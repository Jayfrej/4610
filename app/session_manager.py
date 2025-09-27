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

            self._copy_user_profile_to_instance(instance_path)

            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO accounts (account, nickname, status, pid, created) VALUES (?, ?, COALESCE((SELECT status FROM accounts WHERE account=?),'Offline'), COALESCE((SELECT pid FROM accounts WHERE account=?), NULL), COALESCE((SELECT created FROM accounts WHERE account=?), ?))",
                    (account, nickname, account, account, account, datetime.now().isoformat()),
                )
                conn.commit()

            started = self.start_instance(account)
            if not started:
                logger.warning(f"[CREATE_INSTANCE] Instance created but failed to start for {account}")
            return True
        except Exception as e:
            logger.error(f"[CREATE_INSTANCE] Failed for {account}: {e}")
            return False

    def _copy_user_profile_to_instance(self, instance_path: str):
        try:
            src = self.profile_source
            if not src or not os.path.exists(src):
                logger.info(f"[COPY_PROFILE] Profile source not found or not set: {src}")
                return
            items = [
                ("config", "config"),
                ("profiles", "profiles"),
                ("MQL5", "MQL5"),
                ("bases", "Bases"),
            ]
            for sname, dname in items:
                sp = os.path.join(src, sname)
                dp = os.path.join(instance_path, dname)
                if os.path.exists(sp):
                    if os.path.exists(dp):
                        logger.info(f"[COPY_PROFILE] Merging {sname} -> {dname}")
                        self._merge_directories(sp, dp)
                    else:
                        shutil.copytree(sp, dp, dirs_exist_ok=True)
                        logger.info(f"[COPY_PROFILE] ✓ Copied {sname}")
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
        try:
            if self.is_instance_alive(account):
                logger.info(f"[START_INSTANCE] Account {account} already running")
                return True

            inst = self.get_instance_path(account)
            if not os.path.exists(inst):
                logger.error(f"[START_INSTANCE] Instance directory not found: {inst}")
                return False

            exe = os.path.join(inst, "terminal64.exe")
            if not os.path.exists(exe):
                exe = os.path.join(inst, "terminal.exe")
                if not os.path.exists(exe):
                    logger.error(f"[START_INSTANCE] No MT5 executable found in: {inst}")
                    return False

            logger.info(f"[START_INSTANCE] Launching MT5 for {account}")
            proc = subprocess.Popen(
                [exe],
                cwd=inst,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            pid = proc.pid
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
