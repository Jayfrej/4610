import os
import logging
from typing import Dict, Optional, List
from datetime import datetime
import json

# Optional MT5 Python integration
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    logging.warning("MetaTrader5 library not available. Using file-based method only.")

logger = logging.getLogger(__name__)

class MT5Handler:
    """Handle direct MT5 trading operations"""
    
    def __init__(self):
        self.mt5_available = MT5_AVAILABLE
        self.connection_cache = {}  # Cache connections per account
        
        if self.mt5_available:
            logger.info("[MT5_HANDLER] MetaTrader5 library available")
        else:
            logger.info("[MT5_HANDLER] Using file-based trading method")
    
    def send_trading_signal(self, account: str, command: Dict, instance_path: str) -> Dict:
        """Send trading signal to MT5 instance"""
        method = os.getenv('TRADING_METHOD', 'file').lower()
        
        if method == 'direct' and self.mt5_available:
            return self._send_direct_to_mt5(account, command, instance_path)
        else:
            return self._write_command_file(account, command, instance_path)
    
    def _send_direct_to_mt5(self, account: str, command: Dict, instance_path: str) -> Dict:
        """Send command directly to MT5 via Python API"""
        try:
            # Initialize MT5 connection for this instance
            if not self._ensure_mt5_connection(instance_path):
                return {'success': False, 'error': 'Failed to connect to MT5'}
            
            # Get account info to verify connection
            account_info = mt5.account_info()
            if not account_info:
                return {'success': False, 'error': 'No account info available'}
            
            # Verify we're connected to the right account
            if str(account_info.login) != str(account):
                logger.warning(f"[MT5_HANDLER] Account mismatch: connected to {account_info.login}, expected {account}")
            
            # Execute the trading command
            result = self._execute_trading_command(command)
            
            logger.info(f"[MT5_HANDLER] Direct trade result for {account}: {result}")
            return result
            
        except Exception as e:
            error_msg = f"Direct MT5 trading failed: {str(e)}"
            logger.error(f"[MT5_HANDLER] {error_msg}")
            return {'success': False, 'error': error_msg}
    
    def _ensure_mt5_connection(self, instance_path: str) -> bool:
        """Ensure MT5 connection to specific instance"""
        try:
            # Check if already connected to this instance
            if instance_path in self.connection_cache:
                if mt5.terminal_info() and mt5.account_info():
                    return True
            
            # Initialize MT5 with specific path
            mt5_path = os.path.join(instance_path, 'terminal64.exe')
            if os.path.exists(mt5_path):
                success = mt5.initialize(path=mt5_path)
            else:
                # Try default initialization and hope it connects to the right instance
                success = mt5.initialize()
            
            if success:
                self.connection_cache[instance_path] = True
                logger.info(f"[MT5_HANDLER] Connected to MT5 instance: {instance_path}")
                return True
            else:
                logger.error(f"[MT5_HANDLER] Failed to initialize MT5 for {instance_path}")
                return False
                
        except Exception as e:
            logger.error(f"[MT5_HANDLER] Connection error: {str(e)}")
            return False
    
    def _execute_trading_command(self, command: Dict) -> Dict:
        """Execute trading command via MT5 API"""
        try:
            order_type = command.get('order_type', 'market').lower()
            symbol = command['symbol']
            action = command['action']
            volume = float(command['volume'])
            
            # Validate symbol exists
            if not mt5.symbol_select(symbol, True):
                return {'success': False, 'error': f'Symbol {symbol} not found'}
            
            # Get symbol info
            symbol_info = mt5.symbol_info(symbol)
            if not symbol_info:
                return {'success': False, 'error': f'Cannot get symbol info for {symbol}'}
            
            # Check if symbol is available for trading
            if not symbol_info.visible:
                logger.warning(f"[MT5_HANDLER] Symbol {symbol} is not visible, trying to select it")
                if not mt5.symbol_select(symbol, True):
                    return {'success': False, 'error': f'Cannot select symbol {symbol}'}
            
            # Prepare the request based on order type
            if order_type in ['market']:
                return self._execute_market_order(symbol, action, volume, command)
            elif order_type in ['limit', 'stop']:
                return self._execute_pending_order(symbol, action, volume, command)
            elif order_type == 'close':
                return self._close_positions(symbol, command)
            elif order_type == 'close_all':
                return self._close_all_positions()
            else:
                return {'success': False, 'error': f'Unsupported order type: {order_type}'}
                
        except Exception as e:
            error_msg = f"Execute command failed: {str(e)}"
            logger.error(f"[MT5_HANDLER] {error_msg}")
            return {'success': False, 'error': error_msg}
    
    def _execute_market_order(self, symbol: str, action: str, volume: float, command: Dict) -> Dict:
        """Execute market order"""
        try:
            # Determine order type
            if action.upper() == 'BUY':
                order_type = mt5.ORDER_TYPE_BUY
                price = mt5.symbol_info_tick(symbol).ask
            else:  # SELL
                order_type = mt5.ORDER_TYPE_SELL
                price = mt5.symbol_info_tick(symbol).bid
            
            if not price:
                return {'success': False, 'error': f'Cannot get price for {symbol}'}
            
            # Prepare request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": order_type,
                "price": price,
                "deviation": int(command.get('deviation', 20)),
                "magic": int(command.get('magic', 234000)),
                "comment": command.get('comment', 'Python script'),
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            # Add SL/TP if specified
            if 'stop_loss' in command and command['stop_loss']:
                request['sl'] = float(command['stop_loss'])
            if 'take_profit' in command and command['take_profit']:
                request['tp'] = float(command['take_profit'])
            
            # Send order
            result = mt5.order_send(request)
            
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                return {
                    'success': True,
                    'order_id': result.order,
                    'deal_id': result.deal,
                    'volume': result.volume,
                    'price': result.price,
                    'comment': result.comment
                }
            else:
                error_msg = f"Order failed: {result.comment if result else 'Unknown error'}"
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            return {'success': False, 'error': f'Market order failed: {str(e)}'}
    
    def _execute_pending_order(self, symbol: str, action: str, volume: float, command: Dict) -> Dict:
        """Execute pending order (limit/stop)"""
        try:
            order_type_map = {
                ('BUY', 'limit'): mt5.ORDER_TYPE_BUY_LIMIT,
                ('SELL', 'limit'): mt5.ORDER_TYPE_SELL_LIMIT,
                ('BUY', 'stop'): mt5.ORDER_TYPE_BUY_STOP,
                ('SELL', 'stop'): mt5.ORDER_TYPE_SELL_STOP,
            }
            
            order_key = (action.upper(), command.get('order_type', 'limit').lower())
            if order_key not in order_type_map:
                return {'success': False, 'error': f'Invalid pending order type: {order_key}'}
            
            order_type = order_type_map[order_key]
            price = float(command.get('price', 0))
            
            if not price:
                return {'success': False, 'error': 'Price required for pending orders'}
            
            # Prepare request
            request = {
                "action": mt5.TRADE_ACTION_PENDING,
                "symbol": symbol,
                "volume": volume,
                "type": order_type,
                "price": price,
                "magic": int(command.get('magic', 234000)),
                "comment": command.get('comment', 'Python script'),
                "type_time": mt5.ORDER_TIME_GTC,
            }
            
            # Add SL/TP if specified
            if 'stop_loss' in command and command['stop_loss']:
                request['sl'] = float(command['stop_loss'])
            if 'take_profit' in command and command['take_profit']:
                request['tp'] = float(command['take_profit'])
            
            # Send order
            result = mt5.order_send(request)
            
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                return {
                    'success': True,
                    'order_id': result.order,
                    'volume': result.volume,
                    'price': result.price,
                    'comment': result.comment
                }
            else:
                error_msg = f"Pending order failed: {result.comment if result else 'Unknown error'}"
                return {'success': False, 'error': error_msg}
                
        except Exception as e:
            return {'success': False, 'error': f'Pending order failed: {str(e)}'}
    
    def _close_positions(self, symbol: str, command: Dict) -> Dict:
        """Close positions for specific symbol"""
        try:
            positions = mt5.positions_get(symbol=symbol)
            if not positions:
                return {'success': True, 'message': f'No positions found for {symbol}'}
            
            closed_count = 0
            errors = []
            
            for position in positions:
                # Determine close order type
                if position.type == mt5.POSITION_TYPE_BUY:
                    order_type = mt5.ORDER_TYPE_SELL
                    price = mt5.symbol_info_tick(symbol).bid
                else:
                    order_type = mt5.ORDER_TYPE_BUY
                    price = mt5.symbol_info_tick(symbol).ask
                
                # Prepare close request
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": position.volume,
                    "type": order_type,
                    "position": position.ticket,
                    "price": price,
                    "deviation": int(command.get('deviation', 20)),
                    "magic": position.magic,
                    "comment": f"Close {position.ticket}",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                
                result = mt5.order_send(request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    closed_count += 1
                else:
                    errors.append(f"Failed to close {position.ticket}: {result.comment if result else 'Unknown'}")
            
            if errors:
                return {'success': False, 'error': f'Closed {closed_count} positions with errors: {"; ".join(errors)}'}
            else:
                return {'success': True, 'message': f'Closed {closed_count} positions for {symbol}'}
                
        except Exception as e:
            return {'success': False, 'error': f'Close positions failed: {str(e)}'}
    
    def _close_all_positions(self) -> Dict:
        """Close all open positions"""
        try:
            positions = mt5.positions_get()
            if not positions:
                return {'success': True, 'message': 'No positions to close'}
            
            closed_count = 0
            errors = []
            
            for position in positions:
                symbol = position.symbol
                
                # Determine close order type
                if position.type == mt5.POSITION_TYPE_BUY:
                    order_type = mt5.ORDER_TYPE_SELL
                    price = mt5.symbol_info_tick(symbol).bid
                else:
                    order_type = mt5.ORDER_TYPE_BUY
                    price = mt5.symbol_info_tick(symbol).ask
                
                # Prepare close request
                request = {
                    "action": mt5.TRADE_ACTION_DEAL,
                    "symbol": symbol,
                    "volume": position.volume,
                    "type": order_type,
                    "position": position.ticket,
                    "price": price,
                    "deviation": 20,
                    "magic": position.magic,
                    "comment": f"Close all {position.ticket}",
                    "type_time": mt5.ORDER_TIME_GTC,
                    "type_filling": mt5.ORDER_FILLING_IOC,
                }
                
                result = mt5.order_send(request)
                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    closed_count += 1
                else:
                    errors.append(f"Failed to close {position.ticket}: {result.comment if result else 'Unknown'}")
            
            if errors:
                return {'success': False, 'error': f'Closed {closed_count} positions with errors: {"; ".join(errors)}'}
            else:
                return {'success': True, 'message': f'Closed all {closed_count} positions'}
                
        except Exception as e:
            return {'success': False, 'error': f'Close all positions failed: {str(e)}'}
    
    def _write_command_file(self, account: str, command: Dict, instance_path: str) -> Dict:
        """Write command to file for EA to read (fallback method)"""
        try:
            # Create MQL5/Files directory if not exists
            files_dir = os.path.join(instance_path, 'MQL5', 'Files')
            if not os.path.exists(files_dir):
                os.makedirs(files_dir)
            
            # Generate unique filename
            timestamp = int(datetime.now().timestamp() * 1000)
            filename = f"webhook_command_{timestamp}.json"
            filepath = os.path.join(files_dir, filename)
            
            # Write command to file
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(command, f, ensure_ascii=False, indent=2)
            
            logger.info(f"[MT5_HANDLER] Command written to file: {filepath}")
            return {
                'success': True, 
                'method': 'file',
                'filepath': filepath,
                'message': 'Command written to file for EA processing'
            }
            
        except Exception as e:
            error_msg = f"Failed to write command file: {str(e)}"
            logger.error(f"[MT5_HANDLER] {error_msg}")
            return {'success': False, 'error': error_msg}
    
    def get_account_info(self, instance_path: str) -> Optional[Dict]:
        """Get MT5 account information"""
        if not self.mt5_available:
            return None
            
        try:
            if self._ensure_mt5_connection(instance_path):
                account_info = mt5.account_info()
                if account_info:
                    return {
                        'login': account_info.login,
                        'balance': account_info.balance,
                        'equity': account_info.equity,
                        'margin': account_info.margin,
                        'free_margin': account_info.margin_free,
                        'currency': account_info.currency,
                        'server': account_info.server,
                        'company': account_info.company
                    }
            return None
        except Exception as e:
            logger.error(f"[MT5_HANDLER] Failed to get account info: {str(e)}")
            return None
    
    def get_positions(self, instance_path: str, symbol: str = None) -> List[Dict]:
        """Get open positions"""
        if not self.mt5_available:
            return []
            
        try:
            if self._ensure_mt5_connection(instance_path):
                if symbol:
                    positions = mt5.positions_get(symbol=symbol)
                else:
                    positions = mt5.positions_get()
                
                if positions:
                    return [
                        {
                            'ticket': pos.ticket,
                            'symbol': pos.symbol,
                            'type': 'BUY' if pos.type == mt5.POSITION_TYPE_BUY else 'SELL',
                            'volume': pos.volume,
                            'price_open': pos.price_open,
                            'price_current': pos.price_current,
                            'profit': pos.profit,
                            'comment': pos.comment
                        }
                        for pos in positions
                    ]
            return []
        except Exception as e:
            logger.error(f"[MT5_HANDLER] Failed to get positions: {str(e)}")
            return []
    
    def cleanup(self):
        """Cleanup MT5 connections"""
        if self.mt5_available:
            try:
                mt5.shutdown()
                self.connection_cache.clear()
                logger.info("[MT5_HANDLER] MT5 connections cleaned up")
            except Exception as e:
                logger.error(f"[MT5_HANDLER] Cleanup error: {str(e)}")
    
    def __del__(self):
        """Destructor to ensure cleanup"""
        self.cleanup()