import os
import logging
from typing import List, Optional, Dict
import json
import time

# Optional MT5 Python integration
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False

logger = logging.getLogger(__name__)

class SymbolFetcher:
    """Fetch available symbols from MT5 instances"""
    
    def __init__(self):
        self.mt5_available = MT5_AVAILABLE
        self.symbol_cache = {}
        self.cache_expiry = 3600  # 1 hour cache
        
        if self.mt5_available:
            logger.info("[SYMBOL_FETCHER] MetaTrader5 library available for symbol fetching")
        else:
            logger.info("[SYMBOL_FETCHER] Using file-based symbol fetching")
    
    def fetch_symbols_from_instance(self, account: str, instance_path: str) -> List[str]:
        """Fetch symbols from specific MT5 instance"""
        # Check cache first
        cache_key = f"{account}_{instance_path}"
        if self._is_cache_valid(cache_key):
            return self.symbol_cache[cache_key]['symbols']
        
        symbols = []
        
        if self.mt5_available:
            symbols = self._fetch_via_mt5_api(instance_path)
        
        # Fallback to file-based method
        if not symbols:
            symbols = self._fetch_via_files(instance_path)
        
        # Update cache
        self.symbol_cache[cache_key] = {
            'symbols': symbols,
            'timestamp': time.time()
        }
        
        logger.info(f"[SYMBOL_FETCHER] Fetched {len(symbols)} symbols from {account}")
        return symbols
    
    def _fetch_via_mt5_api(self, instance_path: str) -> List[str]:
        """Fetch symbols using MT5 Python API"""
        try:
            # Try to connect to the MT5 instance
            mt5_path = os.path.join(instance_path, 'terminal64.exe')
            if os.path.exists(mt5_path):
                success = mt5.initialize(path=mt5_path)
            else:
                success = mt5.initialize()
            
            if not success:
                logger.warning("[SYMBOL_FETCHER] Failed to initialize MT5")
                return []
            
            # Get all symbols
            symbols_info = mt5.symbols_get()
            if not symbols_info:
                logger.warning("[SYMBOL_FETCHER] No symbols available")
                return []
            
            # Filter to get only visible symbols (in Market Watch)
            visible_symbols = []
            for symbol_info in symbols_info:
                if symbol_info.visible:
                    visible_symbols.append(symbol_info.name)
            
            # Get additional symbols from Market Watch
            market_watch_symbols = self._get_market_watch_symbols()
            
            # Combine and deduplicate
            all_symbols = list(set(visible_symbols + market_watch_symbols))
            all_symbols.sort()
            
            logger.info(f"[SYMBOL_FETCHER] Found {len(all_symbols)} symbols via API")
            return all_symbols
            
        except Exception as e:
            logger.error(f"[SYMBOL_FETCHER] API fetch failed: {str(e)}")
            return []
        finally:
            try:
                mt5.shutdown()
            except:
                pass
    
    def _get_market_watch_symbols(self) -> List[str]:
        """Get symbols currently in Market Watch"""
        try:
            symbols = []
            
            # Try to get symbols from Market Watch
            # This is a bit tricky as MT5 API doesn't have direct Market Watch access
            # We'll get all visible symbols as approximation
            all_symbols = mt5.symbols_get()
            if all_symbols:
                for symbol in all_symbols:
                    if symbol.visible and symbol.select:
                        symbols.append(symbol.name)
            
            return symbols
            
        except Exception as e:
            logger.error(f"[SYMBOL_FETCHER] Market Watch fetch failed: {str(e)}")
            return []
    
    def _fetch_via_files(self, instance_path: str) -> List[str]:
        """Fetch symbols from MT5 configuration files"""
        symbols = []
        
        try:
            # Method 1: Read from symbols.sel (Market Watch)
            symbols_sel_path = os.path.join(instance_path, 'config', 'symbols.sel')
            if os.path.exists(symbols_sel_path):
                symbols.extend(self._parse_symbols_sel(symbols_sel_path))
            
            # Method 2: Read from terminal log files
            symbols.extend(self._parse_terminal_logs(instance_path))
            
            # Method 3: Common symbols as fallback
            if not symbols:
                symbols = self._get_common_symbols()
            
            # Remove duplicates and sort
            symbols = list(set(symbols))
            symbols.sort()
            
            logger.info(f"[SYMBOL_FETCHER] Found {len(symbols)} symbols via files")
            return symbols
            
        except Exception as e:
            logger.error(f"[SYMBOL_FETCHER] File fetch failed: {str(e)}")
            return self._get_common_symbols()
    
    def _parse_symbols_sel(self, file_path: str) -> List[str]:
        """Parse symbols.sel file for Market Watch symbols"""
        symbols = []
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
                
                # symbols.sel is a binary file, we need to extract symbol names
                # This is a simplified parser - might need adjustment
                content_str = content.decode('utf-8', errors='ignore')
                
                # Look for patterns that might be symbol names
                import re
                potential_symbols = re.findall(r'[A-Z]{3,10}', content_str)
                
                # Filter to likely symbols
                for symbol in potential_symbols:
                    if self._is_likely_symbol(symbol):
                        symbols.append(symbol)
            
            logger.info(f"[SYMBOL_FETCHER] Parsed {len(symbols)} symbols from symbols.sel")
            
        except Exception as e:
            logger.error(f"[SYMBOL_FETCHER] Failed to parse symbols.sel: {str(e)}")
        
        return symbols
    
    def _parse_terminal_logs(self, instance_path: str) -> List[str]:
        """Parse terminal log files for symbol information"""
        symbols = []
        try:
            logs_dir = os.path.join(instance_path, 'Logs')
            if not os.path.exists(logs_dir):
                return symbols
            
            # Look for recent log files
            log_files = []
            for file in os.listdir(logs_dir):
                if file.endswith('.log'):
                    log_path = os.path.join(logs_dir, file)
                    log_files.append((log_path, os.path.getmtime(log_path)))
            
            # Sort by modification time, newest first
            log_files.sort(key=lambda x: x[1], reverse=True)
            
            # Parse the most recent log files
            for log_path, _ in log_files[:3]:  # Check up to 3 recent logs
                try:
                    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        
                        # Look for symbol mentions in logs
                        import re
                        
                        # Common patterns in MT5 logs
                        patterns = [
                            r"symbol '([A-Z0-9]{3,10})'",
                            r"'([A-Z0-9]{3,10})' symbol",
                            r"([A-Z]{6}) ",  # Common forex pairs
                            r"([A-Z]{3}USD)",  # USD pairs
                            r"(USD[A-Z]{3})",  # USD pairs
                            r"(XAU[A-Z]{3})",  # Gold pairs
                            r"(XAG[A-Z]{3})",  # Silver pairs
                        ]
                        
                        for pattern in patterns:
                            matches = re.findall(pattern, content)
                            for match in matches:
                                if self._is_likely_symbol(match):
                                    symbols.append(match)
                
                except Exception as e:
                    logger.debug(f"[SYMBOL_FETCHER] Failed to parse log {log_path}: {str(e)}")
                    continue
            
            # Remove duplicates
            symbols = list(set(symbols))
            logger.info(f"[SYMBOL_FETCHER] Found {len(symbols)} symbols from logs")
            
        except Exception as e:
            logger.error(f"[SYMBOL_FETCHER] Log parsing failed: {str(e)}")
        
        return symbols
    
    def _is_likely_symbol(self, text: str) -> bool:
        """Check if text looks like a trading symbol"""
        if not text or len(text) < 3:
            return False
        
        # Common symbol patterns
        common_patterns = [
            # Forex majors
            'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'USDCAD', 'AUDUSD', 'NZDUSD',
            # Forex minors
            'EURJPY', 'GBPJPY', 'CHFJPY', 'EURGBP', 'EURAUD', 'GBPAUD',
            # Metals
            'XAUUSD', 'XAGUSD', 'XAUEUR', 'XAGEUR',
            # Oils
            'USOIL', 'UKOIL', 'NGAS',
            # Crypto
            'BTCUSD', 'ETHUSD', 'LTCUSD', 'XRPUSD',
            # Indices
            'US30', 'US500', 'NAS100', 'GER30', 'UK100', 'JP225', 'AUS200'
        ]
        
        # Check against known patterns
        if text in common_patterns:
            return True
        
        # Check pattern matching
        import re
        
        # Forex pairs pattern
        if re.match(r'^[A-Z]{3}[A-Z]{3}$', text):
            return True
        
        # Index pattern
        if re.match(r'^[A-Z]{2,3}\d{2,3}$', text):
            return True
        
        # Metal pattern
        if text.startswith(('XAU', 'XAG', 'XPD', 'XPT')):
            return True
        
        # Crypto pattern
        if text.endswith('USD') and len(text) >= 6:
            return True
        
        # Oil pattern
        if text in ['USOIL', 'UKOIL', 'BRENT', 'WTI']:
            return True
        
        return False
    
    def _get_common_symbols(self) -> List[str]:
        """Get list of common trading symbols as fallback"""
        return [
            # Forex Majors
            'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF', 'USDCAD', 'AUDUSD', 'NZDUSD',
            # Forex Minors
            'EURJPY', 'GBPJPY', 'CHFJPY', 'EURGBP', 'EURAUD', 'GBPAUD', 'AUDCAD',
            'AUDCHF', 'AUDJPY', 'AUDNZD', 'CADCHF', 'CADJPY', 'CHFJPY', 'EURAUD',
            'EURCAD', 'EURCHF', 'EURGBP', 'EURJPY', 'EURNZD', 'GBPAUD', 'GBPCAD',
            'GBPCHF', 'GBPJPY', 'GBPNZD', 'NZDCAD', 'NZDCHF', 'NZDJPY', 'NZDUSD',
            
            # Metals
            'XAUUSD', 'XAGUSD', 'XAUEUR', 'XAGEUR', 'XPDUSD', 'XPTUSD',
            
            # Energies
            'USOIL', 'UKOIL', 'NGAS', 'BRENT', 'WTI',
            
            # Indices
            'US30', 'US500', 'NAS100', 'GER30', 'UK100', 'JP225', 'AUS200',
            'FRA40', 'SPA35', 'ITA40', 'NED25', 'SWI20', 'HK50', 'CHINA50',
            
            # Cryptocurrencies
            'BTCUSD', 'ETHUSD', 'LTCUSD', 'XRPUSD', 'BCHUSD', 'ADAUSD', 'DOTUSD',
            'LINKUSD', 'XLMUSD', 'EOSUSD', 'TRXUSD', 'ETCUSD', 'DASHUSD', 'ZECUSD',
            
            # Commodities
            'COPPER', 'SUGAR', 'COTTON', 'COFFEE', 'COCOA', 'WHEAT', 'CORN', 'SOYBEAN'
        ]
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached data is still valid"""
        if cache_key not in self.symbol_cache:
            return False
        
        cache_time = self.symbol_cache[cache_key]['timestamp']
        return (time.time() - cache_time) < self.cache_expiry
    
    def fetch_all_symbols(self, accounts_data: List[Dict]) -> Dict[str, List[str]]:
        """Fetch symbols from all active accounts"""
        all_symbols = {}
        
        for account_info in accounts_data:
            account = account_info['account']
            if account_info.get('status') != 'Online':
                continue
            
            try:
                from .session_manager import SessionManager
                session_manager = SessionManager()
                instance_path = session_manager.get_instance_path(account)
                
                if instance_path:
                    symbols = self.fetch_symbols_from_instance(account, instance_path)
                    all_symbols[account] = symbols
                
            except Exception as e:
                logger.error(f"[SYMBOL_FETCHER] Failed to fetch symbols for {account}: {str(e)}")
                all_symbols[account] = []
        
        return all_symbols
    
    def get_unified_symbol_list(self, accounts_data: List[Dict]) -> List[str]:
        """Get unified list of all symbols from all accounts"""
        all_symbols_data = self.fetch_all_symbols(accounts_data)
        
        # Combine all symbols
        unified_symbols = set()
        for symbols in all_symbols_data.values():
            unified_symbols.update(symbols)
        
        # Convert to sorted list
        unified_list = list(unified_symbols)
        unified_list.sort()
        
        logger.info(f"[SYMBOL_FETCHER] Unified symbol list contains {len(unified_list)} symbols")
        return unified_list
    
    def save_symbols_to_file(self, symbols: List[str], filename: str = "available_symbols.json"):
        """Save symbols list to file"""
        try:
            os.makedirs('data', exist_ok=True)
            filepath = os.path.join('data', filename)
            
            data = {
                'timestamp': time.time(),
                'symbols': symbols,
                'count': len(symbols)
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[SYMBOL_FETCHER] Saved {len(symbols)} symbols to {filepath}")
            
        except Exception as e:
            logger.error(f"[SYMBOL_FETCHER] Failed to save symbols: {str(e)}")
    
    def load_symbols_from_file(self, filename: str = "available_symbols.json") -> List[str]:
        """Load symbols list from file"""
        try:
            filepath = os.path.join('data', filename)
            if not os.path.exists(filepath):
                return []
            
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check if data is recent (less than 24 hours old)
            if time.time() - data.get('timestamp', 0) > 86400:
                logger.warning("[SYMBOL_FETCHER] Loaded symbols are more than 24 hours old")
            
            symbols = data.get('symbols', [])
            logger.info(f"[SYMBOL_FETCHER] Loaded {len(symbols)} symbols from {filepath}")
            return symbols
            
        except Exception as e:
            logger.error(f"[SYMBOL_FETCHER] Failed to load symbols: {str(e)}")
            return []
    
    def update_symbol_whitelist(self, symbol_mapper, accounts_data: List[Dict]):
        """Update symbol mapper whitelist with current symbols"""
        try:
            # Try to load from file first (faster)
            symbols = self.load_symbols_from_file()
            
            # If no cached symbols or too old, fetch fresh
            if not symbols:
                symbols = self.get_unified_symbol_list(accounts_data)
                if symbols:
                    self.save_symbols_to_file(symbols)
            
            # Update symbol mapper whitelist
            if symbols:
                symbol_mapper.set_symbol_whitelist(symbols)
                logger.info(f"[SYMBOL_FETCHER] Updated symbol mapper whitelist with {len(symbols)} symbols")
            
        except Exception as e:
            logger.error(f"[SYMBOL_FETCHER] Failed to update whitelist: {str(e)}")
    
    def clear_cache(self):
        """Clear symbol cache"""
        self.symbol_cache.clear()
        logger.info("[SYMBOL_FETCHER] Symbol cache cleared")
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        return {
            'cached_accounts': len(self.symbol_cache),
            'cache_expiry_seconds': self.cache_expiry,
            'mt5_available': self.mt5_available
        }
    
    def test_symbol_fetch(self, instance_path: str) -> Dict:
        """Test symbol fetching for debugging"""
        result = {
            'mt5_api_available': self.mt5_available,
            'instance_path_exists': os.path.exists(instance_path),
            'methods_tested': {},
            'symbols_found': []
        }
        
        # Test MT5 API method
        if self.mt5_available:
            try:
                symbols = self._fetch_via_mt5_api(instance_path)
                result['methods_tested']['mt5_api'] = {
                    'success': len(symbols) > 0,
                    'count': len(symbols),
                    'error': None
                }
                if symbols:
                    result['symbols_found'].extend(symbols[:10])  # First 10 symbols
            except Exception as e:
                result['methods_tested']['mt5_api'] = {
                    'success': False,
                    'count': 0,
                    'error': str(e)
                }
        
        # Test file method
        try:
            symbols = self._fetch_via_files(instance_path)
            result['methods_tested']['file_based'] = {
                'success': len(symbols) > 0,
                'count': len(symbols),
                'error': None
            }
            if symbols and not result['symbols_found']:
                result['symbols_found'].extend(symbols[:10])  # First 10 symbols
        except Exception as e:
            result['methods_tested']['file_based'] = {
                'success': False,
                'count': 0,
                'error': str(e)
            }
        
        # Test common symbols fallback
        common_symbols = self._get_common_symbols()
        result['methods_tested']['common_fallback'] = {
            'success': True,
            'count': len(common_symbols),
            'error': None
        }
        
        return result