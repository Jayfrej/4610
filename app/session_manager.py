import os
import shutil
import subprocess
import time
import json
import logging
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional

try:
    import psutil  # process management
except Exception:
    psutil = None  # we'll guard usage

logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

class SessionManager:
    """
    Manages per-account portable MT5 instances.
    """

    def __init__(self):
        self.base_dir = os.path.abspath(os.getcwd())
        self.instances_dir = os.path.abspath(
            os.getenv("MT5_INSTANCES_DIR", os.path.join(self.base_dir, "mt5_instances"))
        )
        os.makedirs(self.instances_dir, exist_ok=True)
        self.mt5_path = os.getenv("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")
        self.profile_source = os.getenv("MT5_PROFILE_SOURCE") or self._auto_detect_profile_source()
        data_dir = os.path.join(self.base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = os.path.join(data_dir, "accounts.db")
        self._init_db()

    # -------------------------- DB --------------------------
    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    account TEXT PRIMARY KEY,
                    nickname TEXT,
                    status TEXT,
                    pid INTEGER,
                    created TEXT
                )
                """
            )
            conn.commit()

    def get_all_accounts(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT account, nickname, status, pid, created FROM accounts ORDER BY account"
            ).fetchall()
            return [dict(r) for r in rows]

    def account_exists(self, account: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM accounts WHERE account = ?", (account,)
            ).fetchone()
            return row is not None

    def update_account_status(self, account: str, status: str, pid: Optional[int] = None):
        with sqlite3.connect(self.db_path) as conn:
            if pid is not None:
                conn.execute(
                    "UPDATE accounts SET status = ?, pid = ? WHERE account = ?",
                    (status, pid, account),
                )
            else:
                conn.execute(
                    "UPDATE accounts SET status = ? WHERE account = ?",
                    (status, account),
                )
            conn.commit()

    # ---------------------- Paths & Detect ----------------------
    def get_instance_path(self, account: str) -> str:
        return os.path.join(self.instances_dir, str(account))

    def get_bat_path(self, account: str) -> str:
        """Get path to the BAT launcher file for this account"""
        instance_path = self.get_instance_path(account)
        return os.path.join(instance_path, f"launch_mt5_{account}.bat")

    def _auto_detect_profile_source(self) -> Optional[str]:
        appdata = os.getenv("APPDATA")
        if not appdata:
            return None
        candidates_root = os.path.join(appdata, "MetaQuotes", "Terminal")
        if not os.path.isdir(candidates_root):
            return None
        newest = None
        newest_mtime = 0
        for child in os.listdir(candidates_root):
            p = os.path.join(candidates_root, child)
            if os.path.isdir(p) and os.path.exists(os.path.join(p, "MQL5")):
                mtime = os.path.getmtime(p)
                if mtime > newest_mtime:
                    newest_mtime = mtime
                    newest = p
        return newest

    def diagnose_profile_source(self) -> Dict:
        p = self.profile_source
        info = {"exists": bool(p and os.path.exists(p)), "path": p}
        if info["exists"]:
            info["subdirs"] = [d for d in ("config", "profiles", "MQL5", "bases") if os.path.exists(os.path.join(p, d))]
        return info

    # -------------------- BAT File Creation --------------------
    def create_bat_launcher(self, account: str) -> bool:
        """Create a BAT file to launch MT5 in portable mode for this account"""
        try:
            instance_path = self.get_instance_path(account)
            bat_path = self.get_bat_path(account)
            
            # Find MT5 executable in instance
            terminal_exe = os.path.join(instance_path, "terminal64.exe")
            if not os.path.exists(terminal_exe):
                terminal_exe = os.path.join(instance_path, "terminal.exe")
                if not os.path.exists(terminal_exe):
                    logger.error(f"[CREATE_BAT] No MT5 executable found in: {instance_path}")
                    return False
            
            # Create portable data path
            data_path = os.path.join(instance_path, "Data")
            os.makedirs(data_path, exist_ok=True)
            
            # Create BAT content with portable mode
            bat_content = f'''@echo off
REM Auto-generated BAT launcher for MT5 Account {account}
REM This launches MT5 in portable mode with dedicated data path

echo Starting MT5 for Account {account} in Portable Mode...
echo Data Path: {data_path}
echo Instance Path: {instance_path}

cd /d "{instance_path}"

REM Launch MT5 with portable mode and custom data path
"{terminal_exe}" /portable /datapath="{data_path}"

pause
'''
            
            # Write BAT file
            with open(bat_path, 'w', encoding='utf-8') as f:
                f.write(bat_content)
            
            logger.info(f"[CREATE_BAT] ✓ Created BAT launcher: {bat_path}")
            return True
            
        except Exception as e:
            logger.error(f"[CREATE_BAT] Failed to create BAT for {account}: {e}")
            return False

    def launch_bat_file(self, account: str) -> bool:
        """Launch the BAT file for this account"""
        try:
            bat_path = self.get_bat_path(account)
            if not os.path.exists(bat_path):
                logger.error(f"[LAUNCH_BAT] BAT file not found: {bat_path}")
                return False
            
            logger.info(f"[LAUNCH_BAT] Launching BAT: {bat_path}")
            
            # Launch BAT file
            proc = subprocess.Popen(
                [bat_path],
                cwd=os.path.dirname(bat_path),
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                shell=True
            )
            
            # Give it a moment to start
            time.sleep(2)
            
            # Try to get the actual MT5 process PID
            pid = self._find_mt5_pid_for_account(account)
            if pid:
                self.update_account_status(account, "Online", pid)
                logger.info(f"[LAUNCH_BAT] ✓ MT5 started for {account}, PID: {pid}")
                return True
            else:
                logger.warning(f"[LAUNCH_BAT] BAT launched but MT5 PID not found for {account}")
                self.update_account_status(account, "Starting", None)
                return True  # Still consider success since BAT launched
                
        except Exception as e:
            logger.error(f"[LAUNCH_BAT] Failed to launch BAT for {account}: {e}")
            return False

    def _find_mt5_pid_for_account(self, account: str) -> Optional[int]:
        """Try to find the MT5 process PID for this account"""
        if psutil is None:
            return None
        
        try:
            instance_path = os.path.abspath(self.get_instance_path(account))
            
            for proc in psutil.process_iter(["pid", "name", "exe", "cwd"]):
                try:
                    name = (proc.info.get("name") or "").lower()
                    if name not in ("terminal64.exe", "terminal.exe"):
                        continue
                    
                    exe = proc.info.get("exe") or ""
                    cwd = proc.info.get("cwd") or ""
                    
                    # Check if this process is running from our instance
                    if (instance_path in os.path.abspath(exe) or 
                        instance_path in os.path.abspath(cwd)):
                        return proc.info["pid"]
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
                    
        except Exception as e:
            logger.debug(f"[FIND_PID] Error finding PID for {account}: {e}")
            
        return None

    # -------------------- MT5 Process Utils --------------------
    def _close_all_mt5_processes(self):
        """Terminate only MT5-related processes we own. Never wait() on all system processes."""
        if psutil is None:
            logger.warning("[PROCESS] psutil not installed; cannot close MT5 processes automatically.")
            return
        names = {"terminal64.exe", "terminal.exe", "metatester64.exe", "metaeditor64.exe"}
        targets = []
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                try:
                    name = (proc.info.get("name") or "").lower()
                    if name in names:
                        targets.append(proc)
                except Exception:
                    continue
            # terminate gently
            for proc in targets:
                try:
                    proc.terminate()
                except Exception:
                    pass
            psutil.wait_procs(targets, timeout=3)
            # kill survivors
            survivors = []
            for proc in targets:
                try:
                    if proc.is_running():
                        survivors.append(proc)
                except Exception:
                    continue
            for proc in survivors:
                try:
                    proc.kill()
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"[PROCESS] Best-effort close MT5 processes raised: {e}")

    def _iter_instance_procs(self, account: str):
        if psutil is None:
            return
        inst = os.path.abspath(self.get_instance_path(account))
        for proc in psutil.process_iter(["pid", "name", "exe", "cwd"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if name not in ("terminal64.exe", "terminal.exe"):
                    continue
                exe = proc.info.get("exe") or ""
                cwd = proc.info.get("cwd") or ""
                if inst in os.path.abspath(exe) or inst in os.path.abspath(cwd):
                    yield proc
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    def is_instance_alive(self, account: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT pid FROM accounts WHERE account = ?", (account,)).fetchone()
            pid = row[0] if row else None

        if psutil and pid:
            try:
                proc = psutil.Process(pid)
                if proc.is_running():
                    return True
            except psutil.Error:
                pass

        if psutil:
            for _ in self._iter_instance_procs(account):
                return True
        return False

    # -------------------- Create / Start / Stop --------------------
    def ensure_instance(self, account: str, nickname: str = "") -> bool:
        """Compat helper: create if missing, else start if stopped."""
        inst = self.get_instance_path(account)
        if not os.path.exists(inst):
            return self.create_instance(account, nickname=nickname)
        if not self.is_instance_alive(account):
            return self.start_instance(account)
        return True

    def create_instance(self, account: str, nickname: str = "") -> bool:
        """Create instance, generate BAT file, and launch it automatically"""
        try:
            if self.account_exists(account):
                logger.info(f"[CREATE_INSTANCE] Account {account} already exists in DB; continuing.")
            
            # Close MT5 files locks
            logger.info("[CREATE_INSTANCE] Closing all MT5 processes...")
            self._close_all_mt5_processes()
            time.sleep(1)

            mt5_program_path = os.path.dirname(self.mt5_path)
            if not os.path.exists(mt5_program_path):
                logger.error(f"[CREATE_INSTANCE] MT5 program folder not found: {mt5_program_path}")
                return False

            instance_path = self.get_instance_path(account)
            if os.path.exists(instance_path):
                try:
                    shutil.rmtree(instance_path)
                except Exception as e:
                    logger.error(f"[CREATE_INSTANCE] Could not remove old instance: {e}")
                    return False

            logger.info(f"[CREATE_INSTANCE] Copying MT5 program -> {instance_path}")
            os.makedirs(os.path.dirname(instance_path), exist_ok=True)

            try:
                shutil.copytree(mt5_program_path, instance_path, dirs_exist_ok=True)
            except Exception as e:
                logger.warning(f"[CREATE_INSTANCE] Full copy failed, trying selective copy: {e}")
                os.makedirs(instance_path, exist_ok=True)
                essential_items = [
                    "terminal64.exe", "terminal.exe", "MetaEditor64.exe",
                    "metatester64.exe", "Bases", "Config", "Profiles",
                    "Sounds", "MQL5", "Terminal.ico", "uninstall.exe",
                ]
                for item in essential_items:
                    src = os.path.join(mt5_program_path, item)
                    dst = os.path.join(instance_path, item)
                    if os.path.exists(src):
                        try:
                            if os.path.isdir(src):
                                shutil.copytree(src, dst, dirs_exist_ok=True)
                            else:
                                shutil.copy2(src, dst)
                            logger.info(f"[CREATE_INSTANCE] ✓ Copied {item}")
                        except Exception as item_err:
                            logger.warning(f"[CREATE_INSTANCE] Failed to copy {item}: {item_err}")

            # Copy user profile to instance (if available)
            self._copy_user_profile_to_instance(instance_path)
            
            # Create portable data directory structure
            self._create_portable_data_structure(instance_path)

            # Add to database
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO accounts (account, nickname, status, pid, created) VALUES (?, ?, COALESCE((SELECT status FROM accounts WHERE account=?),'Offline'), COALESCE((SELECT pid FROM accounts WHERE account=?), NULL), COALESCE((SELECT created FROM accounts WHERE account=?), ?))",
                    (account, nickname, account, account, account, datetime.now().isoformat()),
                )
                conn.commit()

            # Create BAT launcher
            logger.info(f"[CREATE_INSTANCE] Creating BAT launcher for {account}...")
            if not self.create_bat_launcher(account):
                logger.error(f"[CREATE_INSTANCE] Failed to create BAT launcher for {account}")
                return False
            
            # Launch the BAT file immediately
            logger.info(f"[CREATE_INSTANCE] Auto-launching MT5 for {account}...")
            if not self.launch_bat_file(account):
                logger.warning(f"[CREATE_INSTANCE] Instance created but failed to auto-launch for {account}")
                # Don't return False here - instance creation was successful
            
            logger.info(f"[CREATE_INSTANCE] ✓ Successfully created and launched instance for {account}")
            return True
            
        except Exception as e:
            logger.error(f"[CREATE_INSTANCE] Failed for {account}: {e}")
            return False

    def _create_portable_data_structure(self, instance_path: str):
        """Create the portable data directory structure"""
        try:
            data_path = os.path.join(instance_path, "Data")
            
            # Create essential directories for portable mode
            directories = [
                data_path,
                os.path.join(data_path, "MQL5"),
                os.path.join(data_path, "MQL5", "Files"),
                os.path.join(data_path, "MQL5", "Include"),
                os.path.join(data_path, "MQL5", "Experts"),
                os.path.join(data_path, "MQL5", "Indicators"),
                os.path.join(data_path, "MQL5", "Scripts"),
                os.path.join(data_path, "config"),
                os.path.join(data_path, "profiles"),
                os.path.join(data_path, "bases"),
                os.path.join(data_path, "logs"),
            ]
            
            for dir_path in directories:
                os.makedirs(dir_path, exist_ok=True)
                
            logger.info(f"[PORTABLE_STRUCTURE] ✓ Created portable data structure in {data_path}")
            
        except Exception as e:
            logger.warning(f"[PORTABLE_STRUCTURE] Failed to create structure: {e}")

    def _copy_user_profile_to_instance(self, instance_path: str):
        """Copy user profile data to both instance and portable data directory"""
        try:
            src = self.profile_source
            if not src or not os.path.exists(src):
                logger.info(f"[COPY_PROFILE] Profile source not found or not set: {src}")
                return
            
            # Copy to both locations for compatibility
            data_path = os.path.join(instance_path, "Data")
            
            items = [
                ("config", "config"),
                ("profiles", "profiles"),
                ("MQL5", "MQL5"),
                ("bases", "bases"),
            ]
            
            for sname, dname in items:
                sp = os.path.join(src, sname)
                if not os.path.exists(sp):
                    continue
                
                # Copy to instance root (traditional location)
                dp_instance = os.path.join(instance_path, dname)
                # Copy to Data folder (portable location)
                dp_data = os.path.join(data_path, dname)
                
                for dp in [dp_instance, dp_data]:
                    try:
                        if os.path.exists(dp):
                            logger.info(f"[COPY_PROFILE] Merging {sname} -> {dp}")
                            self._merge_directories(sp, dp)
                        else:
                            shutil.copytree(sp, dp, dirs_exist_ok=True)
                            logger.info(f"[COPY_PROFILE] ✓ Copied {sname} -> {dp}")
                    except Exception as e:
                        logger.warning(f"[COPY_PROFILE] Failed to copy {sname} to {dp}: {e}")
                        
        except Exception as e:
            logger.warning(f"[COPY_PROFILE] Error: {e}")

    def _merge_directories(self, src_dir: str, dst_dir: str):
        for root, dirs, files in os.walk(src_dir):
            rel = os.path.relpath(root, src_dir)
            dst_root = dst_dir if rel == "." else os.path.join(dst_dir, rel)
            os.makedirs(dst_root, exist_ok=True)
            for f in files:
                s = os.path.join(root, f)
                d = os.path.join(dst_root, f)
                try:
                    shutil.copy2(s, d)
                except Exception as e:
                    logger.debug(f"[MERGE_DIRS] Skip {f}: {e}")

    def start_instance(self, account: str) -> bool:
        """Start instance using BAT file (preferred) or direct execution"""
        try:
            if self.is_instance_alive(account):
                logger.info(f"[START_INSTANCE] Account {account} already running")
                return True

            inst = self.get_instance_path(account)
            if not os.path.exists(inst):
                logger.error(f"[START_INSTANCE] Instance directory not found: {inst}")
                return False

            # Try to use BAT file first (portable mode)
            bat_path = self.get_bat_path(account)
            if os.path.exists(bat_path):
                logger.info(f"[START_INSTANCE] Using BAT launcher for {account}")
                return self.launch_bat_file(account)
            
            # Fallback to direct execution (legacy method)
            logger.info(f"[START_INSTANCE] BAT not found, using direct launch for {account}")
            
            exe = os.path.join(inst, "terminal64.exe")
            if not os.path.exists(exe):
                exe = os.path.join(inst, "terminal.exe")
                if not os.path.exists(exe):
                    logger.error(f"[START_INSTANCE] No MT5 executable found in: {inst}")
                    return False

            # Try to launch with portable mode even without BAT
            data_path = os.path.join(inst, "Data")
            os.makedirs(data_path, exist_ok=True)
            
            logger.info(f"[START_INSTANCE] Launching MT5 for {account} with portable mode")
            proc = subprocess.Popen(
                [exe, "/portable", f"/datapath={data_path}"],
                cwd=inst,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            
            time.sleep(2)
            pid = self._find_mt5_pid_for_account(account) or proc.pid
            self.update_account_status(account, "Online", pid)
            return True
            
        except Exception as e:
            logger.error(f"[START_INSTANCE] Failed for {account}: {e}")
            return False

    def stop_instance(self, account: str) -> bool:
        ok = True
        if psutil is None:
            logger.warning("[STOP_INSTANCE] psutil not installed; cannot stop gracefully.")
            return False
        try:
            for proc in list(self._iter_instance_procs(account)):
                try:
                    proc.terminate()
                except Exception:
                    ok = False
            time.sleep(2)
            for proc in list(self._iter_instance_procs(account)):
                try:
                    proc.kill()
                except Exception:
                    ok = False
            self.update_account_status(account, "Offline", None)
            return ok
        except Exception as e:
            logger.error(f"[STOP_INSTANCE] Failed for {account}: {e}")
            return False

    def restart_instance(self, account: str) -> bool:
        stopped = self.stop_instance(account)
        time.sleep(1)
        started = self.start_instance(account)
        return stopped and started

    def delete_instance(self, account: str) -> bool:
        try:
            self.stop_instance(account)
            inst = self.get_instance_path(account)
            if os.path.exists(inst):
                shutil.rmtree(inst, ignore_errors=True)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM accounts WHERE account = ?", (account,))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"[DELETE_INSTANCE] Failed for {account}: {e}")
            return False

    def focus_instance(self, account: str) -> bool:
        try:
            import pygetwindow as gw  # optional
        except Exception:
            logger.info("[FOCUS] pygetwindow not available; skipping focus.")
            return False
        try:
            wins = [w for w in gw.getAllTitles() if "meta" in w.lower() or "trader" in w.lower()]
            if wins:
                win = gw.getWindowsWithTitle(wins[0])[0]
                win.activate()
                return True
        except Exception as e:
            logger.debug(f"[FOCUS] Unable to focus window: {e}")
        return False
