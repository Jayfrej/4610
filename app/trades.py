# trades.py
# Lightweight trade history service (file-backed + SSE)
# - Stores JSONL at data/trades.jsonl
# - In-memory ring buffer for fast reads
# - REST:   GET /trades?limit=&status=&symbol=&account=&since=
# - SSE:    GET /events/trades
# - Helper: record_and_broadcast(event_dict)

from __future__ import annotations

import os
import json
import time
import queue
import threading
from collections import deque
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from flask import Blueprint, Response, jsonify, request, stream_with_context, current_app

trades_bp = Blueprint("trades", __name__)

# ---- Storage & in-memory buffer ------------------------------------------------

DATA_PATH = os.path.join("data", "trades.jsonl")
MAX_BUFFER = int(os.getenv("TRADES_MAX_BUFFER", "1000"))  # latest N kept in memory
_buffer: deque[Dict[str, Any]] = deque(maxlen=MAX_BUFFER)
_lock = threading.RLock()

_clients: List["queue.Queue[str]"] = []  # SSE subscribers
HEARTBEAT_SECS = 20

def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

def _ensure_data_folder():
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)

def _tail_jsonl(path: str, max_items: int) -> Iterable[Dict[str, Any]]:
    """Read up to last max_items JSON lines (simple & safe)."""
    if not os.path.exists(path):
        return []
    items: deque[Dict[str, Any]] = deque(maxlen=max_items)
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                # skip malformed lines
                continue
    return list(items)

def _append_to_store(evt: Dict[str, Any]) -> None:
    _ensure_data_folder()
    with open(DATA_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(evt, ensure_ascii=False) + "\n")

def _rewrite_store(events: List[Dict[str, Any]]) -> None:
    """Rewrite entire file with filtered events"""
    _ensure_data_folder()
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        for evt in events:
            f.write(json.dumps(evt, ensure_ascii=False) + "\n")

def _normalize_event(evt: Dict[str, Any]) -> Dict[str, Any]:
    # fill defaults
    if "id" not in evt:
        evt["id"] = str(int(time.time() * 1000))
    if "timestamp" not in evt:
        evt["timestamp"] = _utcnow_iso()

    # common field aliases (frontend may expect these names)
    if "account" not in evt and "account_number" in evt:
        evt["account"] = evt["account_number"]

    return evt

def init_trades() -> None:
    """Call once on startup (e.g., in server.py) to warm the buffer."""
    with _lock:
        recent = _tail_jsonl(DATA_PATH, MAX_BUFFER)
        _buffer.clear()
        for evt in recent:
            _buffer.appendleft(evt)  # newest first (left side)
    current_app.logger.info(f"[TRADES] Buffer warmed with {len(_buffer)} events")

def record_and_broadcast(evt: Dict[str, Any]) -> None:
    """Public API: call this after a trade action (success/error)."""
    evt = _normalize_event(evt)
    with _lock:
        _buffer.appendleft(evt)
        try:
            _append_to_store(evt)
        except Exception as e:
            current_app.logger.error(f"[TRADES] Failed to persist: {e}", exc_info=True)

        payload = f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
        dead: List[queue.Queue[str]] = []
        for q in _clients:
            try:
                q.put_nowait(payload)
            except Exception:
                dead.append(q)
        for q in dead:
            if q in _clients:
                _clients.remove(q)

def delete_account_history(account: str) -> int:
    """Delete all history for specific account. Returns count of deleted items."""
    with _lock:
        # Remove from buffer
        original_count = len(_buffer)
        _buffer_list = list(_buffer)
        _buffer.clear()
        
        kept_count = 0
        for evt in _buffer_list:
            evt_account = str(evt.get("account", evt.get("account_number", "")))
            if evt_account != str(account):
                _buffer.append(evt)
                kept_count += 1
        
        deleted_from_buffer = original_count - kept_count
        
        # Rewrite file without this account's trades
        try:
            if os.path.exists(DATA_PATH):
                all_trades = []
                with open(DATA_PATH, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            evt = json.loads(line)
                            evt_account = str(evt.get("account", evt.get("account_number", "")))
                            if evt_account != str(account):
                                all_trades.append(evt)
                        except Exception:
                            continue
                
                _rewrite_store(all_trades)
                current_app.logger.info(f"[TRADES] Deleted history for account {account}")
        except Exception as e:
            current_app.logger.error(f"[TRADES] Failed to delete account history: {e}", exc_info=True)
        
        # Broadcast update to all clients
        try:
            payload = f"data: {json.dumps({'event': 'account_deleted', 'account': account}, ensure_ascii=False)}\n\n"
            for q in _clients:
                try:
                    q.put_nowait(payload)
                except Exception:
                    pass
        except Exception:
            pass
        
        return deleted_from_buffer

# ---- Filters & REST ------------------------------------------------------------

def _match(evt: Dict[str, Any],
           status: Optional[str],
           symbol: Optional[str],
           account: Optional[str],
           since_iso: Optional[str]) -> bool:
    if status and str(evt.get("status", "")).lower() != status.lower():
        return False
    if symbol and str(evt.get("symbol", "")).upper() != symbol.upper():
        return False
    if account and str(evt.get("account", evt.get("account_number", ""))) != str(account):
        return False
    if since_iso:
        try:
            # simple compare by string if both ISO-like; else fall back
            if str(evt.get("timestamp", "")) < since_iso:
                return False
        except Exception:
            pass
    return True

@trades_bp.route("/trades", methods=["GET"])
def get_trades():
    """
    Query params:
      - limit  : int (1..1000, default 100)
      - status : success | error
      - symbol : e.g., XAUUSD
      - account: account number
      - since  : ISO8601 (UTC) e.g., 2025-09-30T00:00:00Z
    """
    limit = int(request.args.get("limit", 100))
    limit = max(1, min(limit, 1000))

    status = request.args.get("status") or None
    symbol = request.args.get("symbol") or None
    account = request.args.get("account") or None
    since = request.args.get("since") or None

    with _lock:
        result: List[Dict[str, Any]] = []
        for evt in _buffer:
            if _match(evt, status, symbol, account, since):
                result.append(evt)
                if len(result) >= limit:
                    break

    return jsonify({"trades": result, "count": len(result)})

@trades_bp.route("/trades/clear", methods=["POST"])
def clear_trades():
    """Clear file + buffer (require confirm=1)."""
    if request.args.get("confirm") != "1":
        return jsonify({"ok": False, "error": "Missing confirm=1"}), 400

    with _lock:
        _buffer.clear()
        try:
            _ensure_data_folder()
            # ✅ ลบไฟล์จริงๆ แทนการเขียนทับด้วยไฟล์ว่าง
            if os.path.exists(DATA_PATH):
                os.remove(DATA_PATH)
            current_app.logger.info("[TRADES] History cleared - file deleted")
        except Exception as e:
            current_app.logger.error(f"[TRADES] Clear failed: {e}", exc_info=True)
            return jsonify({"ok": False, "error": str(e)}), 500

    # Broadcast clear event to all clients
    try:
        payload = f"data: {json.dumps({'event': 'history_cleared'}, ensure_ascii=False)}\n\n"
        for q in _clients:
            try:
                q.put_nowait(payload)
            except Exception:
                pass
    except Exception:
        pass

    return jsonify({"ok": True})

# ---- SSE -----------------------------------------------------------------------

@trades_bp.route("/events/trades", methods=["GET"])
def sse_trades():
    """
    Server-Sent Events stream of trades.
    - Sends 'retry' hint.
    - Heartbeats every HEARTBEAT_SECS to keep connection alive.
    """
    q: "queue.Queue[str]" = queue.Queue(maxsize=256)
    _clients.append(q)

    last_beat = time.time()

    def gen():
        nonlocal last_beat
        try:
            # reconnection hint
            yield "retry: 3000\n\n"
            while True:
                try:
                    # heartbeat
                    now = time.time()
                    if now - last_beat >= HEARTBEAT_SECS:
                        last_beat = now
                        yield ": keep-alive\n\n"

                    msg = q.get(timeout=1.0)  # check heartbeat each second
                    yield msg
                except queue.Empty:
                    # just loop for heartbeat
                    continue
        finally:
            # client disconnected
            try:
                _clients.remove(q)
            except ValueError:
                pass

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
    }
    return Response(stream_with_context(gen()), headers=headers)
