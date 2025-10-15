"""
Copy Trading Handler
รับและประมวลผลสัญญาณจาก Master EA
Version: 2.1 - Fixed Copy TP/SL Toggle
"""

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class CopyHandler:
    """จัดการการรับและประมวลผลสัญญาณจาก Master"""
    
    def __init__(self, copy_manager, symbol_mapper, copy_executor, session_manager):
        self.copy_manager = copy_manager
        self.symbol_mapper = symbol_mapper
        self.copy_executor = copy_executor

        # ✅ เพิ่ม BalanceHelper สำหรับ Percent Mode
        from .balance_helper import BalanceHelper
        self.balance_helper = BalanceHelper(session_manager)

        logger.info("[COPY_HANDLER] Initialized successfully (Order Tracking Enabled)")
    
    def process_master_signal(self, api_key: str, signal_data: Dict) -> Dict:
        """
        ประมวลผลสัญญาณจาก Master EA
        
        Args:
            api_key: API Key ของ Copy Pair
            signal_data: ข้อมูล Signal จาก Master {
                'event': 'deal_add' | 'deal_close' | 'position_modify',
                'order_id': 'order_12345',  # ✅ Unique Order ID
                'account': '111111',
                'symbol': 'XAUUSD',
                'type': 'BUY' | 'SELL',
                'volume': 1.0,
                'tp': 2450.0,
                'sl': 2400.0
            }
            
        Returns:
            Dict: {'success': bool, 'message': str, 'error': str}
        """
        pair: Optional[Dict] = None
        try:
            # 1) ตรวจสอบ API Key และหา Pair
            pair = self.copy_manager.validate_api_key(api_key)
            if not pair:
                logger.warning(f"[COPY_HANDLER] Invalid API key: {api_key[:8]}...")
                return {'success': False, 'error': 'Invalid API key'}
            
            # 2) ตรวจสอบสถานะ Pair
            if pair.get('status') != 'active':
                logger.info(f"[COPY_HANDLER] Pair {pair.get('id')} is inactive")
                return {'success': False, 'error': 'Copy pair is inactive'}
            
            # 3) ตรวจสอบว่าเป็น Master account จริงหรือไม่
            master_account = str(signal_data.get('account', ''))
            if master_account != pair.get('master_account'):
                logger.warning(f"[COPY_HANDLER] Account mismatch: {master_account} != {pair.get('master_account')}")
                return {'success': False, 'error': 'Account mismatch'}
            
            # 4) แปลง Signal → Command
            slave_command = self._convert_signal_to_command(signal_data, pair)
            if not slave_command:
                error_msg = "Cannot convert signal to command"
                logger.warning(f"[COPY_HANDLER] {error_msg}")
                try:
                    self.copy_executor.copy_history.record_copy_event({
                        'status': 'error',
                        'master': master_account,
                        'slave': pair['slave_account'],
                        'action': str(signal_data.get('event', 'UNKNOWN')).upper(),
                        'symbol': signal_data.get('symbol', '-'),
                        'volume': signal_data.get('volume', ''),
                        'message': f'❌ {error_msg}'
                    })
                except Exception:
                    pass
                return {'success': False, 'error': error_msg}
            
            # 5) ตรวจสอบว่า Slave online หรือไม่
            slave_account = pair['slave_account']
            if not self.balance_helper.session_manager.is_instance_alive(slave_account):
                error_msg = f"Slave account {slave_account} is offline"
                logger.warning(f"[COPY_HANDLER] {error_msg}")
                try:
                    self.copy_executor.copy_history.record_copy_event({
                        'status': 'error',
                        'master': master_account,
                        'slave': pair['slave_account'],
                        'action': str(signal_data.get('event', 'UNKNOWN')).upper(),
                        'symbol': signal_data.get('symbol', '-'),
                        'volume': signal_data.get('volume', ''),
                        'message': f'❌ {error_msg}'
                    })
                except Exception:
                    pass
                return {'success': False, 'error': error_msg}
            
            # 6) ส่งคำสั่งไปยัง Slave
            result = self.copy_executor.execute_on_slave(
                slave_account=pair['slave_account'],
                command=slave_command,
                pair=pair
            )
            return result
        
        except Exception as e:
            logger.error(f"[COPY_HANDLER] Error processing signal: {e}", exc_info=True)
            try:
                self.copy_executor.copy_history.record_copy_event({
                    'status': 'error',
                    'master': str(signal_data.get('account', '-')),
                    'slave': (pair.get('slave_account', '-') if isinstance(pair, dict) else '-'),
                    'action': str(signal_data.get('event', 'UNKNOWN')).upper(),
                    'symbol': signal_data.get('symbol', '-'),
                    'volume': signal_data.get('volume', ''),
                    'message': f'❌ Exception: {str(e)}'
                })
            except Exception:
                pass
            return {'success': False, 'error': str(e)}
    
    # ======================
    #  Volume Calculation
    # ======================
    def _calculate_slave_volume(
        self,
        master_volume: float,
        settings: Dict,
        slave_account: str,
        symbol: str
    ) -> float:
        """
        คำนวณ Volume สำหรับ Slave ตาม settings
        
        Volume Modes:
        - multiply: Master Volume × Multiplier
        - fixed: ใช้ค่าคงที่ (Multiplier)
        - percent: คำนวณจาก Risk % ของ Balance
        
        Args:
            master_volume: Volume จาก Master
            settings: การตั้งค่า Pair
            slave_account: หมายเลขบัญชี Slave
            symbol: Symbol ที่จะเทรด
            
        Returns:
            float: Volume ที่คำนวณแล้ว
        """
        try:
            volume_mode = settings.get('volume_mode') or settings.get('volumeMode', 'multiply')
            multiplier = float(settings.get('multiplier', 2))
            
            # ตรวจสอบข้อมูล Symbol
            symbol_info = self.balance_helper.session_manager.get_symbol_info(slave_account, symbol)
            if not symbol_info:
                logger.warning(f"[COPY_HANDLER] Cannot get symbol info for {symbol}, using master volume")
                return max(master_volume, 0.01)
            
            min_lot = float(symbol_info.get('volume_min', 0.01))
            max_lot = float(symbol_info.get('volume_max', 100.0))
            lot_step = float(symbol_info.get('volume_step', 0.01))
            
            # คำนวณ Volume ตาม Mode
            if volume_mode == 'multiply':
                # โหมด Multiply: Volume × Multiplier
                calculated_volume = master_volume * multiplier
                logger.info(f"[COPY_HANDLER] Multiply mode: {master_volume} × {multiplier} = {calculated_volume}")
            
            elif volume_mode == 'fixed':
                # โหมด Fixed: ใช้ค่า Multiplier เป็น Volume คงที่
                calculated_volume = multiplier
                logger.info(f"[COPY_HANDLER] Fixed mode: Volume = {calculated_volume}")
            
            elif volume_mode == 'percent':
                # โหมด Percent: คำนวณจาก % ของ Balance
                balance = self.balance_helper.get_account_balance(slave_account)
                if balance <= 0:
                    logger.warning(f"[COPY_HANDLER] Cannot get balance for {slave_account}, using min lot")
                    return min_lot
                
                # คำนวณ Volume จาก Risk % (multiplier = risk %)
                # สูตร: Volume = (Balance × Risk%) / (SL_Points × Point_Value)
                # ถ้าไม่มี SL ให้ใช้ค่า default
                risk_amount = balance * (multiplier / 100)
                
                # ประมาณ Volume จาก Risk Amount (simplified)
                # ใช้ค่าประมาณ: 1 lot = $10/point สำหรับ Forex
                point_value = 10  # ค่าประมาณ
                calculated_volume = risk_amount / (point_value * 100)
                
                logger.info(
                    f"[COPY_HANDLER] Percent mode: "
                    f"Balance={balance} | Risk={multiplier}% | Volume={calculated_volume}"
                )
            
            else:
                logger.warning(f"[COPY_HANDLER] Unknown volume mode: {volume_mode}, using multiply")
                calculated_volume = master_volume * multiplier
            
            # ✅ ตรวจสอบขอบเขต
            if calculated_volume < min_lot:
                logger.warning(
                    f"[COPY_HANDLER] Volume {calculated_volume} < min_lot {min_lot}, adjusted to {min_lot}"
                )
                calculated_volume = min_lot

            if calculated_volume > max_lot:
                logger.warning(
                    f"[COPY_HANDLER] Volume {calculated_volume} > max_lot {max_lot}, adjusted to {max_lot}"
                )
                calculated_volume = max_lot

            # ✅ ปัดเศษตาม lot_step
            steps = round(calculated_volume / lot_step)
            adjusted_volume = steps * lot_step

            # ตรวจสอบอีกครั้งหลังปัดเศษ
            if adjusted_volume < min_lot:
                adjusted_volume = min_lot

            return round(adjusted_volume, 2)

        except Exception as e:
            logger.error(f"[COPY_HANDLER] Error calculating volume: {e}")
            return max(master_volume, 0.01)

    # ======================
    #  Signal Conversion
    # ======================
    def _convert_signal_to_command(self, signal_data: Dict, pair: Dict) -> Optional[Dict]:
        """
        แปลงสัญญาณจาก Master เป็นคำสั่งสำหรับ Slave
        
        ✅ รองรับ Order Tracking:
        - ใช้ order_id เพื่อสร้าง Unique Comment
        - Slave ค้นหา Order จาก Comment เพื่อปิด/แก้ไขแบบแยกอิสระ
        
        Args:
            signal_data: ข้อมูล Signal จาก Master
            pair: ข้อมูล Copy Pair
            
        Returns:
            Dict: Command สำหรับ Slave EA หรือ None ถ้าแปลงไม่สำเร็จ
        """
        try:
            settings = pair.get('settings', {})
            
            # ✅ Normalize keys (รองรับทั้ง camelCase และ snake_case)
            auto_map_symbol = settings.get('auto_map_symbol') or settings.get('autoMapSymbol', True)
            auto_map_volume = settings.get('auto_map_volume') or settings.get('autoMapVolume', True)
            copy_psl = settings.get('copy_psl') or settings.get('copyPSL', True)
            
            # ดึงข้อมูลพื้นฐาน
            event = str(signal_data.get('event', '')).lower()
            symbol = str(signal_data.get('symbol', ''))
            trade_type = str(signal_data.get('type', '')).upper()
            volume = float(signal_data.get('volume', 0))
            
            # ✅ ดึง order_id จาก Master Signal (สำคัญมาก!)
            order_id = signal_data.get('order_id', '')
            
            logger.info(
                f"[COPY_HANDLER] Converting signal: "
                f"event={event} | symbol={symbol} | type={trade_type} | "
                f"volume={volume} | order_id={order_id}"
            )
            
            # ==================
            # 1. Map Symbol
            # ==================
            if auto_map_symbol:
                mapped_symbol = self.symbol_mapper.map_symbol(symbol)
                if not mapped_symbol:
                    logger.warning(
                        f"[COPY_HANDLER] Cannot map symbol: {symbol}, using original"
                    )
                    mapped_symbol = symbol
                else:
                    logger.info(
                        f"[COPY_HANDLER] Symbol mapped: {symbol} → {mapped_symbol}"
                    )
                symbol = mapped_symbol
            
            # ==================
            # 2. Map Volume
            # ==================
            if auto_map_volume:
                original_volume = volume
                volume = self._calculate_slave_volume(
                    master_volume=volume,
                    settings=settings,
                    slave_account=pair['slave_account'],
                    symbol=symbol
                )
                logger.info(
                    f"[COPY_HANDLER] Volume adjusted: {original_volume} → {volume}"
                )
            
            # ==================
            # 3. สร้าง Comment
            # ==================
            # ✅ Comment Format: COPY_{order_id}
            # ตัวอย่าง: COPY_order_12345
            copy_comment = f"COPY_{order_id}" if order_id else f"Copy from Master {pair['master_account']}"
            
            logger.info(f"[COPY_HANDLER] Generated comment: {copy_comment}")
            
            # ==================
            # 4. สร้างคำสั่งตาม Event Type
            # ==================
            
            # --- EVENT: OPEN ORDER ---
            if event in ['deal_add', 'order_add']:
                logger.info(f"[COPY_HANDLER] Processing OPEN ORDER event")
                
                command = {
                    'action': trade_type,  # BUY or SELL
                    'symbol': symbol,
                    'volume': volume,
                    'order_type': 'market',
                    'comment': copy_comment  # ✅ ใส่ Comment เพื่อ Track Order
                }
                
                # ✅ แก้ไข: เช็ค copy_psl ก่อนส่ง TP/SL
                if copy_psl:
                    if signal_data.get('tp') is not None:
                        command['take_profit'] = float(signal_data['tp'])
                        logger.info(f"[COPY_HANDLER] ✅ TP copied: {command['take_profit']}")
                    if signal_data.get('sl') is not None:
                        command['stop_loss'] = float(signal_data['sl'])
                        logger.info(f"[COPY_HANDLER] ✅ SL copied: {command['stop_loss']}")
                    logger.info(f"[COPY_HANDLER] Copy TP/SL is ENABLED")
                else:
                    # ✅ เพิ่ม: Log เมื่อปิด copyPSL
                    logger.info(f"[COPY_HANDLER] ⚠️ Copy TP/SL is DISABLED - TP/SL will NOT be copied")
                
                logger.info(
                    f"[COPY_HANDLER] ✅ OPEN Command created: "
                    f"{trade_type} {symbol} {volume} lots | Comment: {copy_comment} | "
                    f"TP: {command.get('take_profit', 'N/A')} | SL: {command.get('stop_loss', 'N/A')}"
                )
                return command
            
            # --- EVENT: CLOSE ORDER ---
            elif event in ['deal_close', 'position_close']:
                logger.info(f"[COPY_HANDLER] Processing CLOSE ORDER event")
                
                if order_id:
                    # ✅ มี order_id → ปิดแบบแยกอิสระ (ใช้ Comment)
                    command = {
                        'action': 'CLOSE',
                        'command_type': 'close_position',
                        'comment': copy_comment,  # ✅ Slave EA จะค้นหา Order จาก Comment นี้
                        'symbol': symbol,
                        'volume': volume if auto_map_volume else None
                    }
                    logger.info(
                        f"[COPY_HANDLER] ✅ CLOSE Command created (by Comment): "
                        f"Comment: {copy_comment} | Symbol: {symbol}"
                    )
                    return command
                else:
                    # ⚠️ ไม่มี order_id → Fallback: ปิดทั้งหมดของ Symbol
                    logger.warning(
                        f"[COPY_HANDLER] No order_id provided, "
                        f"falling back to CLOSE_SYMBOL (will close ALL orders of {symbol})"
                    )
                    command = {
                        'action': 'CLOSE_SYMBOL',
                        'symbol': symbol,
                        'volume': volume if auto_map_volume else None
                    }
                    logger.info(
                        f"[COPY_HANDLER] ⚠️ CLOSE_SYMBOL Command created: "
                        f"Symbol: {symbol} (ALL orders will be closed)"
                    )
                    return command
            
            # --- EVENT: MODIFY TP/SL ---
            elif event == 'position_modify':
                logger.info(f"[COPY_HANDLER] Processing MODIFY TP/SL event")
                
                if copy_psl and order_id:
                    # ✅ มี order_id และเปิด copyPSL → แก้ไขแบบแยกอิสระ (ใช้ Comment)
                    command = {
                        'action': 'MODIFY',
                        'command_type': 'modify_position',
                        'comment': copy_comment,  # ✅ Slave EA จะค้นหา Order จาก Comment นี้
                        'symbol': symbol,
                        'take_profit': (
                            float(signal_data.get('tp', 0)) 
                            if signal_data.get('tp') is not None 
                            else None
                        ),
                        'stop_loss': (
                            float(signal_data.get('sl', 0)) 
                            if signal_data.get('sl') is not None 
                            else None
                        )
                    }
                    logger.info(
                        f"[COPY_HANDLER] ✅ MODIFY Command created (by Comment): "
                        f"Comment: {copy_comment} | TP: {command.get('take_profit')} | "
                        f"SL: {command.get('stop_loss')}"
                    )
                    return command
                else:
                    if not copy_psl:
                        logger.info(
                            f"[COPY_HANDLER] copyPSL is disabled, ignoring MODIFY event"
                        )
                    if not order_id:
                        logger.warning(
                            f"[COPY_HANDLER] No order_id provided, cannot modify specific order"
                        )
                    return None
            
            # --- UNKNOWN EVENT ---
            logger.warning(f"[COPY_HANDLER] ⚠️ Unknown event type: {event}")
            return None
            
        except Exception as e:
            logger.error(
                f"[COPY_HANDLER] ❌ Error converting signal: {e}", 
                exc_info=True
            )
            return None


# =================== Testing & Debugging ===================

def test_copy_handler():
    """
    ฟังก์ชันทดสอบ CopyHandler
    
    Test Cases:
    1. Open Order with order_id
    2. Close Order with order_id
    3. Modify Order with order_id
    4. Fallback: Close without order_id
    """
    print("\n" + "="*80)
    print("🧪 Testing CopyHandler - Order Tracking System")
    print("="*80)
    
    # Mock objects
    class MockCopyManager:
        def validate_api_key(self, key):
            return {
                'id': 'pair_001',
                'status': 'active',
                'master_account': '111111',
                'slave_account': '222222',
                'settings': {
                    'auto_map_symbol': True,
                    'auto_map_volume': True,
                    'copy_psl': True,
                    'volume_mode': 'multiply',
                    'multiplier': 2.0
                }
            }
    
    class MockSymbolMapper:
        def map_symbol(self, symbol):
            return symbol  # No mapping
    
    class MockCopyExecutor:
        class MockCopyHistory:
            def record_copy_event(self, event):
                print(f"  📝 Event Recorded: {event}")
        
        def __init__(self):
            self.copy_history = self.MockCopyHistory()
        
        def execute_on_slave(self, slave_account, command, pair):
            print(f"  ✅ Command sent to Slave: {command}")
            return {'success': True}
    
    class MockSessionManager:
        def account_exists(self, account):
            return True
        def is_instance_alive(self, account):
            return True
    
    # Initialize handler
    handler = CopyHandler(
        MockCopyManager(),
        MockSymbolMapper(),
        MockCopyExecutor(),
        MockSessionManager()
    )
    
    # Test Case 1: Open Order
    print("\n📌 Test Case 1: OPEN ORDER with order_id")
    print("-" * 80)
    signal_open = {
        'event': 'deal_add',
        'order_id': 'order_12345',
        'account': '111111',
        'symbol': 'XAUUSD',
        'type': 'BUY',
        'volume': 1.0,
        'tp': 2450.0,
        'sl': 2400.0
    }
    result = handler.process_master_signal('test_key', signal_open)
    print(f"Result: {result}")
    
    # Test Case 2: Close Order
    print("\n📌 Test Case 2: CLOSE ORDER with order_id")
    print("-" * 80)
    signal_close = {
        'event': 'deal_close',
        'order_id': 'order_12345',
        'account': '111111',
        'symbol': 'XAUUSD',
        'volume': 1.0
    }
    result = handler.process_master_signal('test_key', signal_close)
    print(f"Result: {result}")
    
    # Test Case 3: Modify Order
    print("\n📌 Test Case 3: MODIFY ORDER with order_id")
    print("-" * 80)
    signal_modify = {
        'event': 'position_modify',
        'order_id': 'order_12345',
        'account': '111111',
        'symbol': 'XAUUSD',
        'tp': 2460.0,
        'sl': 2410.0
    }
    result = handler.process_master_signal('test_key', signal_modify)
    print(f"Result: {result}")
    
    # Test Case 4: Fallback - Close without order_id
    print("\n📌 Test Case 4: FALLBACK - CLOSE without order_id")
    print("-" * 80)
    signal_close_fallback = {
        'event': 'deal_close',
        'account': '111111',
        'symbol': 'XAUUSD',
        'volume': 1.0
        # ❌ No order_id
    }
    result = handler.process_master_signal('test_key', signal_close_fallback)
    print(f"Result: {result}")
    
    print("\n" + "="*80)
    print("✅ All tests completed!")
    print("="*80 + "\n")


if __name__ == '__main__':
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    
    # Run tests
    test_copy_handler()
