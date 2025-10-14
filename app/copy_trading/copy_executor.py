
import os
import json
import time
import logging
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class CopyExecutor:
    """ส่งคำสั่งการเทรดไปยัง Slave account"""

    def __init__(self, session_manager, copy_history):
        self.session_manager = session_manager
        self.copy_history = copy_history

    # ========================= Public API =========================

    def execute_on_slave(self, slave_account: str, command: Dict[str, Any], pair: Dict[str, Any]) -> Dict[str, Any]:
        """
        ส่งคำสั่งไปยัง Slave account พร้อมตรวจสอบสถานะ
        """
        try:
            # 🔴 1) ตรวจสอบว่าบัญชี Slave มีอยู่จริง
            if not self.session_manager.account_exists(slave_account):
                error_msg = f"Slave account {slave_account} not found in system"
                logger.error(f"[COPY_EXECUTOR] {error_msg}")

                self.copy_history.record_copy_event({
                    'status': 'error',
                    'master': pair.get('master_account', '-'),
                    'slave': slave_account,
                    'action': command.get('action', 'UNKNOWN'),
                    'symbol': command.get('symbol', '-'),
                    'volume': command.get('volume', ''),
                    'message': f'❌ {error_msg}'
                })
                return {'success': False, 'error': error_msg}

            # 🔴 2) ตรวจสอบว่า Slave ออนไลน์
            if not self.session_manager.is_instance_alive(slave_account):
                error_msg = f"Slave account {slave_account} is offline"
                logger.warning(f"[COPY_EXECUTOR] {error_msg}")

                self.copy_history.record_copy_event({
                    'status': 'error',
                    'master': pair.get('master_account', '-'),
                    'slave': slave_account,
                    'action': command.get('action', 'UNKNOWN'),
                    'symbol': command.get('symbol', '-'),
                    'volume': command.get('volume', ''),
                    'message': f'⚠️ {error_msg}'
                })
                return {'success': False, 'error': error_msg}

            # ✅ บัญชีผ่านการตรวจสอบ — เตรียมคำสั่งสำหรับ Slave
            full_command: Dict[str, Any] = {
                **command,
                'account': slave_account,
                'timestamp': datetime.now().isoformat(),
                'copy_from': pair.get('master_account', '-')
            }

            # เขียนคำสั่งลงไฟล์สำหรับ EA
            success = self._write_command_file(slave_account, full_command)

            if success:
                # ✅ บันทึกประวัติสำเร็จ
                self.copy_history.record_copy_event({
                    'status': 'success',
                    'master': pair.get('master_account', '-'),
                    'slave': slave_account,
                    'action': command.get('action', 'UNKNOWN'),
                    'symbol': command.get('symbol', '-'),
                    'volume': command.get('volume', ''),
                    'message': "✅ Command sent to slave EA"
                })

                logger.info(
                    f"[COPY_EXECUTOR] ✓ Command sent to {slave_account}: "
                    f"{command.get('action')} {command.get('symbol')}"
                )
                return {'success': True, 'message': 'Command sent to slave account'}

            # ❌ เขียนไฟล์ไม่สำเร็จ
            error_msg = "Failed to write command file"
            self.copy_history.record_copy_event({
                'status': 'error',
                'master': pair.get('master_account', '-'),
                'slave': slave_account,
                'action': command.get('action', 'UNKNOWN'),
                'symbol': command.get('symbol', '-'),
                'volume': command.get('volume', ''),
                'message': f'❌ {error_msg}'
            })
            return {'success': False, 'error': error_msg}

        except Exception as e:
            error_msg = f"Execution error: {str(e)}"
            logger.error(f"[COPY_EXECUTOR] {error_msg}", exc_info=True)

            self.copy_history.record_copy_event({
                'status': 'error',
                'master': pair.get('master_account', '-'),
                'slave': slave_account,
                'action': command.get('action', 'UNKNOWN'),
                'symbol': command.get('symbol', '-'),
                'volume': command.get('volume', ''),
                'message': f'❌ {error_msg}'
            })
            return {'success': False, 'error': error_msg}

    # ========================= Internal Helpers =========================

    def _write_command_file(self, account: str, command: Dict[str, Any]) -> bool:
        """
        ✅ FIXED: เขียนคำสั่งลงไฟล์ให้ EA ฝั่ง Slave อ่าน
        
        Path: {instance_path}/MQL5/Files/slave_command_{timestamp}.json
        Pattern: slave_command_*.json (ตรงกับที่ EA อ่าน)
        
        Args:
            account: หมายเลขบัญชี Slave
            command: คำสั่งที่จะส่ง
            
        Returns:
            bool: True ถ้าสำเร็จ
        """
        try:
            # ดึง instance path ของ Slave
            instance_path = self.session_manager.get_instance_path(account)
            
            if not os.path.exists(instance_path):
                logger.error(f"[COPY_EXECUTOR] Instance path not found: {instance_path}")
                return False
            
            # สร้าง path ไปยัง MQL5/Files (ที่ EA อ่าน)
            mql5_files_dir = os.path.join(instance_path, "MQL5", "Files")
            os.makedirs(mql5_files_dir, exist_ok=True)
            
            # สร้างชื่อไฟล์ตาม pattern ที่ EA อ่าน: slave_command_*.json
            timestamp = int(time.time() * 1000)
            cmd_file = os.path.join(mql5_files_dir, f"slave_command_{timestamp}.json")
            
            # เขียนไฟล์ JSON
            with open(cmd_file, 'w', encoding='utf-8') as f:
                json.dump(command, f, ensure_ascii=False, indent=2)
            
            logger.info(f"[COPY_EXECUTOR] ✅ Wrote command file: {cmd_file}")
            logger.debug(f"[COPY_EXECUTOR] Command content: {json.dumps(command, indent=2)}")
            return True

        except Exception as e:
            logger.error(f"[COPY_EXECUTOR] ❌ Failed to write command file: {e}", exc_info=True)
            return False

    # ========================= Additional Helpers =========================

    def cleanup_old_commands(self, account: str, max_age_seconds: int = 300) -> int:
        """
        ล้างไฟล์คำสั่งเก่าที่ค้างอยู่ (เกิน 5 นาที)
        
        Args:
            account: หมายเลขบัญชี
            max_age_seconds: อายุไฟล์สูงสุด (วินาที)
            
        Returns:
            int: จำนวนไฟล์ที่ลบ
        """
        try:
            instance_path = self.session_manager.get_instance_path(account)
            mql5_files_dir = os.path.join(instance_path, "MQL5", "Files")
            
            if not os.path.exists(mql5_files_dir):
                return 0
            
            deleted_count = 0
            current_time = time.time()
            
            # สแกนไฟล์ทั้งหมด
            for filename in os.listdir(mql5_files_dir):
                if not filename.startswith("slave_command_") or not filename.endswith(".json"):
                    continue
                
                filepath = os.path.join(mql5_files_dir, filename)
                
                # เช็คอายุไฟล์
                file_age = current_time - os.path.getmtime(filepath)
                
                if file_age > max_age_seconds:
                    try:
                        os.remove(filepath)
                        deleted_count += 1
                        logger.info(f"[COPY_EXECUTOR] Cleaned up old command file: {filename}")
                    except Exception as e:
                        logger.warning(f"[COPY_EXECUTOR] Failed to delete {filename}: {e}")
            
            if deleted_count > 0:
                logger.info(f"[COPY_EXECUTOR] Cleaned up {deleted_count} old command files for {account}")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"[COPY_EXECUTOR] Cleanup error: {e}")
            return 0

    def get_pending_commands(self, account: str) -> list:
        """
        ดึงรายการคำสั่งที่รอ EA อ่าน
        
        Args:
            account: หมายเลขบัญชี
            
        Returns:
            list: รายการไฟล์คำสั่งที่รออยู่
        """
        try:
            instance_path = self.session_manager.get_instance_path(account)
            mql5_files_dir = os.path.join(instance_path, "MQL5", "Files")
            
            if not os.path.exists(mql5_files_dir):
                return []
            
            pending = []
            
            for filename in os.listdir(mql5_files_dir):
                if filename.startswith("slave_command_") and filename.endswith(".json"):
                    filepath = os.path.join(mql5_files_dir, filename)
                    
                    # อ่านข้อมูลไฟล์
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            command = json.load(f)
                        
                        pending.append({
                            'filename': filename,
                            'filepath': filepath,
                            'command': command,
                            'age_seconds': int(time.time() - os.path.getmtime(filepath))
                        })
                    except Exception as e:
                        logger.warning(f"[COPY_EXECUTOR] Failed to read {filename}: {e}")
            
            return pending
            
        except Exception as e:
            logger.error(f"[COPY_EXECUTOR] Get pending commands error: {e}")
            return []

    def test_write_access(self, account: str) -> bool:
        """
        ทดสอบการเขียนไฟล์ (สำหรับ debugging)
        
        Args:
            account: หมายเลขบัญชี
            
        Returns:
            bool: True ถ้าเขียนไฟล์ได้
        """
        try:
            instance_path = self.session_manager.get_instance_path(account)
            mql5_files_dir = os.path.join(instance_path, "MQL5", "Files")
            os.makedirs(mql5_files_dir, exist_ok=True)
            
            # เขียนไฟล์ทดสอบ
            test_file = os.path.join(mql5_files_dir, "test_write.txt")
            with open(test_file, 'w') as f:
                f.write("Test write access")
            
            # ลบไฟล์ทดสอบ
            os.remove(test_file)
            
            logger.info(f"[COPY_EXECUTOR] ✅ Write access test passed for {account}")
            return True
            
        except Exception as e:
            logger.error(f"[COPY_EXECUTOR] ❌ Write access test failed for {account}: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """
        ดึงสถิติการทำงาน
        
        Returns:
            Dict: สถิติการทำงาน
        """
        try:
            all_accounts = self.session_manager.get_all_accounts()
            
            stats = {
                'total_accounts': len(all_accounts),
                'online_accounts': 0,
                'total_pending_commands': 0,
                'accounts': []
            }
            
            for account_info in all_accounts:
                account = account_info['account']
                
                is_online = self.session_manager.is_instance_alive(account)
                if is_online:
                    stats['online_accounts'] += 1
                
                pending = self.get_pending_commands(account)
                stats['total_pending_commands'] += len(pending)
                
                stats['accounts'].append({
                    'account': account,
                    'nickname': account_info.get('nickname', ''),
                    'status': 'online' if is_online else 'offline',
                    'pending_commands': len(pending)
                })
            
            return stats
            
        except Exception as e:
            logger.error(f"[COPY_EXECUTOR] Get stats error: {e}")
            return {'error': str(e)}


# =================== Testing Functions ===================

def test_executor():
    """ฟังก์ชันทดสอบ CopyExecutor"""
    print("\n" + "="*60)
    print("Testing CopyExecutor")
    print("="*60)
    
    # สร้าง mock objects
    class MockSessionManager:
        def account_exists(self, account):
            return True
        
        def is_instance_alive(self, account):
            return True
        
        def get_instance_path(self, account):
            return f"test_instances/{account}"
    
    class MockCopyHistory:
        def record_copy_event(self, event):
            print(f"[MOCK] Recorded event: {event['status']} - {event['message']}")
    
    # สร้าง executor
    session_manager = MockSessionManager()
    copy_history = MockCopyHistory()
    executor = CopyExecutor(session_manager, copy_history)
    
    # ทดสอบเขียนไฟล์
    test_command = {
        'action': 'BUY',
        'symbol': 'BTCUSD',
        'volume': 0.02,
        'order_type': 'market'
    }
    
    test_pair = {
        'master_account': '111111',
        'slave_account': '222222'
    }
    
    print("\n1. Testing execute_on_slave...")
    result = executor.execute_on_slave('222222', test_command, test_pair)
    print(f"Result: {result}")
    
    print("\n2. Testing get_pending_commands...")
    pending = executor.get_pending_commands('222222')
    print(f"Pending commands: {len(pending)}")
    
    print("\n3. Testing cleanup_old_commands...")
    deleted = executor.cleanup_old_commands('222222', max_age_seconds=0)
    print(f"Deleted: {deleted} files")
    
    print("\n" + "="*60)
    print("Testing completed!")
    print("="*60 + "\n")


if __name__ == '__main__':
    # ตั้งค่า logging
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    
    # รันการทดสอบ
    test_executor()