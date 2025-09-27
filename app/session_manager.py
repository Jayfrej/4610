import os
import shutil
import subprocess
import psutil
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional
import sqlite3

logger = logging.getLogger(__name__)

class SessionManager:
    """Manages MT5 instances per account"""
    
    def __init__(self):
        self.mt5_path = os.getenv('MT5_MAIN_PATH', r'C:\Program Files\MetaTrader 5\terminal64.exe')
        self.instances_dir = os.getenv('MT5_INSTANCES_DIR', r'C:\trading_bot\mt5_instances')
        self.profile_source = os.getenv('MT5_PROFILE_SOURCE', r'C:\Users\%USERNAME%\AppData\Roaming\MetaQuotes\Terminal\XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX')
        
        # Expand environment variables
        self.profile_source = os.path.expandvars(self.profile_source)
        self.instances_dir = os.path.expandvars(self.instances_dir)
        
        # Create instances directory if not exists
        if not os.path.exists(self.instances_dir):
            os.makedirs(self.instances_dir)
            logger.info(f"[INIT] Created instances directory: {self.instances_dir}")
        
        # Initialize database
        self.db_path = os.path.join(self.instances_dir, 'accounts.db')
        self._init_database()
        
        logger.info(f"[INIT] SessionManager initialized")
        logger.info(f"[INIT] MT5 Path: {self.mt5_path}")
        logger.info(f"[INIT] Instances Dir: {self.instances_dir}")
        logger.info(f"[INIT] Profile Source: {self.profile_source}")
    
    def _init_database(self):
        """Initialize SQLite database for account management"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS accounts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        account TEXT UNIQUE NOT NULL,
                        nickname TEXT,
                        pid INTEGER,
                        status TEXT DEFAULT 'Offline',
                        created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                conn.commit()
            logger.info("[DB] Database initialized successfully")
        except Exception as e:
            logger.error(f"[DB_ERROR] Failed to initialize database: {str(e)}")
    
    def account_exists(self, account: str) -> bool:
        """Check if account exists in database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('SELECT 1 FROM accounts WHERE account = ?', (account,))
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"[DB_ERROR] Failed to check account existence: {str(e)}")
            return False
    
    def get_all_accounts(self) -> List[Dict]:
        """Get all accounts from database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute('''
                    SELECT id, account, nickname, pid, status, created, last_updated 
                    FROM accounts ORDER BY created DESC
                ''')
                accounts = []
                for row in cursor.fetchall():
                    accounts.append({
                        'id': row['id'],
                        'account': row['account'],
                        'nickname': row['nickname'] or '',
                        'pid': row['pid'],
                        'status': row['status'],
                        'created': row['created'],
                        'last_updated': row['last_updated']
                    })
                return accounts
        except Exception as e:
            logger.error(f"[DB_ERROR] Failed to get accounts: {str(e)}")
            return []
    
    def update_account_status(self, account: str, status: str, pid: Optional[int] = None):
        """Update account status in database"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                if pid is not None:
                    conn.execute('''
                        UPDATE accounts 
                        SET status = ?, pid = ?, last_updated = CURRENT_TIMESTAMP 
                        WHERE account = ?
                    ''', (status, pid, account))
                else:
                    conn.execute('''
                        UPDATE accounts 
                        SET status = ?, last_updated = CURRENT_TIMESTAMP 
                        WHERE account = ?
                    ''', (status, account))
                conn.commit()
        except Exception as e:
            logger.error(f"[DB_ERROR] Failed to update account status: {str(e)}")
    
    def create_instance(self, account: str, nickname: str = "") -> bool:
        """Create new MT5 instance for account"""
        try:
            # Check if account already exists
            if self.account_exists(account):
                logger.warning(f"[CREATE_INSTANCE] Account {account} already exists")
                return False
            
            # Validate profile source
            if not os.path.exists(self.profile_source):
                logger.error(f"[CREATE_INSTANCE] Profile source not found: {self.profile_source}")
                return False
            
            # Check required directories in profile source
            profiles_dir = os.path.join(self.profile_source, 'profiles')
            config_dir = os.path.join(self.profile_source, 'config')
            
            if not os.path.exists(profiles_dir):
                logger.error(f"[CREATE_INSTANCE] Profiles directory not found: {profiles_dir}")
                return False
            
            if not os.path.exists(config_dir):
                logger.error(f"[CREATE_INSTANCE] Config directory not found: {config_dir}")
                return False
            
            # Create instance directory
            instance_path = os.path.join(self.instances_dir, account)
            if os.path.exists(instance_path):
                logger.warning(f"[CREATE_INSTANCE] Instance directory already exists: {instance_path}")
                shutil.rmtree(instance_path)
            
            # Copy profile source to instance directory
            logger.info(f"[CREATE_INSTANCE] Copying profile from {self.profile_source} to {instance_path}")
            shutil.copytree(self.profile_source, instance_path)
            
            # Add account to database
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO accounts (account, nickname, status) 
                    VALUES (?, ?, 'Offline')
                ''', (account, nickname))
                conn.commit()
            
            logger.info(f"[CREATE_INSTANCE] Account {account} created successfully")
            
            # Start the instance
            success = self.start_instance(account)
            return success
            
        except Exception as e:
            logger.error(f"[CREATE_INSTANCE] Failed to create instance for {account}: {str(e)}")
            return False
    
    def start_instance(self, account: str) -> bool:
        """Start MT5 instance for account"""
        try:
            # Check if already running
            if self.is_instance_alive(account):
                logger.info(f"[START_INSTANCE] Account {account} already running")
                return True
            
            instance_path = os.path.join(self.instances_dir, account)
            if not os.path.exists(instance_path):
                logger.error(f"[START_INSTANCE] Instance directory not found: {instance_path}")
                return False
            
            # Build command to start MT5
            cmd = [
                self.mt5_path,
                '/portable',
                f'/datapath:{instance_path}'
            ]
            
            logger.info(f"[START_INSTANCE] Starting MT5 for account {account}")
            logger.debug(f"[START_INSTANCE] Command: {' '.join(cmd)}")
            
            # Start MT5 process
            process = subprocess.Popen(
                cmd,
                cwd=instance_path,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
            
            pid = process.pid
            logger.info(f"[START_INSTANCE] MT5 started for account {account}, PID: {pid}")
            
            # Update database
            self.update_account_status(account, 'Online', pid)
            
            return True
            
        except Exception as e:
            logger.error(f"[START_INSTANCE] Failed to start instance for {account}: {str(e)}")
            return False
    
    def stop_instance(self, account: str) -> bool:
        """Stop MT5 instance for account"""
        try:
            # Get PID from database
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('SELECT pid FROM accounts WHERE account = ?', (account,))
                row = cursor.fetchone()
                
                if not row or not row[0]:
                    logger.warning(f"[STOP_INSTANCE] No PID found for account {account}")
                    return False
                
                pid = row[0]
            
            # Kill process
            if self._kill_process(pid):
                self.update_account_status(account, 'Offline', None)
                logger.info(f"[STOP_INSTANCE] Account {account} stopped (PID: {pid})")
                return True
            else:
                logger.error(f"[STOP_INSTANCE] Failed to stop account {account} (PID: {pid})")
                return False
                
        except Exception as e:
            logger.error(f"[STOP_INSTANCE] Failed to stop instance for {account}: {str(e)}")
            return False
    
    def restart_instance(self, account: str) -> bool:
        """Restart MT5 instance for account"""
        try:
            logger.info(f"[RESTART_INSTANCE] Restarting account {account}")
            
            # Stop first
            self.stop_instance(account)
            
            # Wait a moment
            import time
            time.sleep(2)
            
            # Start again
            return self.start_instance(account)
            
        except Exception as e:
            logger.error(f"[RESTART_INSTANCE] Failed to restart instance for {account}: {str(e)}")
            return False
    
    def delete_instance(self, account: str) -> bool:
        """Delete account and optionally remove instance directory"""
        try:
            # Stop instance first
            self.stop_instance(account)
            
            # Remove from database
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('DELETE FROM accounts WHERE account = ?', (account,))
                conn.commit()
            
            # Optionally remove instance directory
            delete_files = os.getenv('DELETE_INSTANCE_FILES', 'False').lower() == 'true'
            if delete_files:
                instance_path = os.path.join(self.instances_dir, account)
                if os.path.exists(instance_path):
                    shutil.rmtree(instance_path)
                    logger.info(f"[DELETE_INSTANCE] Removed instance directory: {instance_path}")
            
            logger.info(f"[DELETE_INSTANCE] Account {account} deleted successfully")
            return True
            
        except Exception as e:
            logger.error(f"[DELETE_INSTANCE] Failed to delete instance for {account}: {str(e)}")
            return False
    
    def is_instance_alive(self, account: str) -> bool:
        """Check if MT5 instance is running"""
        try:
            # Get PID from database
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('SELECT pid FROM accounts WHERE account = ?', (account,))
                row = cursor.fetchone()
                
                if not row or not row[0]:
                    return False
                
                pid = row[0]
            
            # Check if process is running
            try:
                process = psutil.Process(pid)
                if process.is_running():
                    # Additional check: ensure it's actually MT5
                    if 'terminal64.exe' in process.name().lower() or 'terminal.exe' in process.name().lower():
                        return True
                return False
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return False
                
        except Exception as e:
            logger.error(f"[IS_ALIVE] Failed to check if instance is alive for {account}: {str(e)}")
            return False
    
    def focus_instance(self, account: str) -> bool:
        """Try to focus/bring to front the MT5 instance window"""
        try:
            # Get PID from database
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('SELECT pid FROM accounts WHERE account = ?', (account,))
                row = cursor.fetchone()
                
                if not row or not row[0]:
                    return False
                
                pid = row[0]
            
            # Try to bring window to front using Windows API (if on Windows)
            if os.name == 'nt':
                try:
                    import win32gui
                    import win32con
                    
                    def enum_windows_callback(hwnd, pid_list):
                        if win32gui.GetWindowThreadProcessId(hwnd)[1] == pid:
                            pid_list.append(hwnd)
                        return True
                    
                    windows = []
                    win32gui.EnumWindows(enum_windows_callback, windows)
                    
                    for hwnd in windows:
                        if win32gui.IsWindowVisible(hwnd):
                            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                            win32gui.SetForegroundWindow(hwnd)
                            return True
                except ImportError:
                    logger.warning("[FOCUS_INSTANCE] pywin32 not available, cannot focus window")
            
            return False
            
        except Exception as e:
            logger.error(f"[FOCUS_INSTANCE] Failed to focus instance for {account}: {str(e)}")
            return False
    
    def get_instance_path(self, account: str) -> Optional[str]:
        """Get instance directory path for account"""
        instance_path = os.path.join(self.instances_dir, account)
        return instance_path if os.path.exists(instance_path) else None
    
    def _kill_process(self, pid: int) -> bool:
        """Kill process by PID"""
        try:
            process = psutil.Process(pid)
            
            # Try graceful termination first
            process.terminate()
            
            # Wait for graceful termination
            try:
                process.wait(timeout=10)
                return True
            except psutil.TimeoutExpired:
                # Force kill if graceful termination fails
                logger.warning(f"[KILL_PROCESS] Graceful termination failed for PID {pid}, force killing")
                process.kill()
                process.wait(timeout=5)
                return True
                
        except psutil.NoSuchProcess:
            # Process already dead
            return True
        except Exception as e:
            logger.error(f"[KILL_PROCESS] Failed to kill process {pid}: {str(e)}")
            return False
    
    def get_account_info(self, account: str) -> Optional[Dict]:
        """Get account information"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute('''
                    SELECT id, account, nickname, pid, status, created, last_updated 
                    FROM accounts WHERE account = ?
                ''', (account,))
                row = cursor.fetchone()
                
                if row:
                    return {
                        'id': row['id'],
                        'account': row['account'],
                        'nickname': row['nickname'] or '',
                        'pid': row['pid'],
                        'status': row['status'],
                        'created': row['created'],
                        'last_updated': row['last_updated']
                    }
                return None
        except Exception as e:
            logger.error(f"[GET_ACCOUNT_INFO] Failed to get account info for {account}: {str(e)}")
            return None