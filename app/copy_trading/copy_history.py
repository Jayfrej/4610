"""
Copy Trading History Manager
บันทึกและจัดการประวัติการคัดลอก พร้อม SSE (Server-Sent Events) support
"""

import os
import json
import logging
import time
import queue
import threading
from typing import Dict, List, Optional
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


class CopyHistory:
    """
    จัดการประวัติการคัดลอกการเทรด
    - เก็บข้อมูลใน JSONL file (1 event ต่อ 1 บรรทัด)
    - มี in-memory buffer สำหรับ query ที่เร็ว
    - รองรับ Server-Sent Events (SSE) สำหรับ real-time updates
    """
    
    def __init__(self, max_buffer: int = 1000):
        """
        Initialize Copy History Manager
        
        Args:
            max_buffer: จำนวน events สูงสุดที่เก็บใน memory buffer
        """
        self.data_dir = os.path.join("data")
        os.makedirs(self.data_dir, exist_ok=True)
        
        self.history_file = os.path.join(self.data_dir, "copy_history.jsonl")
        self.max_buffer = max_buffer
        
        # In-memory ring buffer (FIFO)
        self.buffer = deque(maxlen=max_buffer)
        
        # Thread lock สำหรับ concurrent access
        self._lock = threading.RLock()
        
        # SSE clients (list of queues)
        self._clients: List[queue.Queue] = []
        
        # โหลดประวัติล่าสุดเข้า buffer
        self._load_recent_history()
        
        logger.info(f"[COPY_HISTORY] Initialized with {len(self.buffer)} events in buffer")
    
    # =================== Data Loading ===================
    
    def _load_recent_history(self):
        """โหลดประวัติล่าสุดจากไฟล์เข้า buffer"""
        try:
            if not os.path.exists(self.history_file):
                logger.info("[COPY_HISTORY] No history file found, starting fresh")
                return
            
            # อ่านไฟล์ทีละบรรทัด
            events = []
            with open(self.history_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        event = json.loads(line)
                        events.append(event)
                    except json.JSONDecodeError as e:
                        logger.warning(f"[COPY_HISTORY] Skipping invalid JSON line: {e}")
                        continue
            
            # เอาล่าสุด max_buffer events (LIFO - ล่าสุดก่อน)
            recent_events = events[-self.max_buffer:] if len(events) > self.max_buffer else events
            
            # ใส่เข้า buffer (ล่าสุดอยู่ด้านซ้าย)
            for event in reversed(recent_events):
                self.buffer.appendleft(event)
            
            logger.info(f"[COPY_HISTORY] Loaded {len(self.buffer)} recent events from file")
            
        except Exception as e:
            logger.error(f"[COPY_HISTORY] Failed to load history: {e}", exc_info=True)
    
    # =================== Record Events ===================
    
    def record_copy_event(self, event: Dict):
        """
        บันทึกเหตุการณ์การคัดลอก
        
        Event format:
        {
            "status": "success" | "error",
            "master": "12345",
            "slave": "67890",
            "action": "BUY",
            "symbol": "XAUUSD",
            "volume": 1.0,
            "message": "Command sent successfully"
        }
        
        Args:
            event: Dict ข้อมูลเหตุการณ์
        """
        try:
            # เพิ่ม metadata
            if 'id' not in event:
                event['id'] = str(int(time.time() * 1000))
            
            if 'timestamp' not in event:
                event['timestamp'] = datetime.now().isoformat()
            
            # Normalize ข้อมูล
            event = self._normalize_event(event)
            
            with self._lock:
                # เพิ่มเข้า in-memory buffer (ล่าสุดอยู่ด้านซ้าย)
                self.buffer.appendleft(event)
                
                # เขียนลงไฟล์ (append)
                try:
                    with open(self.history_file, 'a', encoding='utf-8') as f:
                        f.write(json.dumps(event, ensure_ascii=False) + '\n')
                except Exception as e:
                    logger.error(f"[COPY_HISTORY] Failed to write to file: {e}")
                
                # Broadcast event ไปยัง SSE clients
                self._broadcast_to_clients(event)
            
            logger.debug(
                f"[COPY_HISTORY] Recorded: {event.get('status')} | "
                f"{event.get('master')} -> {event.get('slave')} | "
                f"{event.get('action')} {event.get('symbol')}"
            )
            
        except Exception as e:
            logger.error(f"[COPY_HISTORY] Failed to record event: {e}", exc_info=True)
    
    def _normalize_event(self, event: Dict) -> Dict:
        """
        Normalize event data
        - แปลง types ให้ถูกต้อง
        - เติมค่า default
        """
        normalized = {}
        
        # Required fields
        normalized['id'] = str(event.get('id', ''))
        normalized['timestamp'] = event.get('timestamp', datetime.now().isoformat())
        normalized['status'] = str(event.get('status', 'unknown')).lower()
        
        # Trading info
        normalized['master'] = str(event.get('master', '-'))
        normalized['slave'] = str(event.get('slave', '-'))
        normalized['action'] = str(event.get('action', 'UNKNOWN')).upper()
        normalized['symbol'] = str(event.get('symbol', '-'))
        
        # Optional fields
        if 'volume' in event:
            try:
                normalized['volume'] = float(event['volume'])
            except (ValueError, TypeError):
                normalized['volume'] = event.get('volume', '')
        else:
            normalized['volume'] = ''
        
        if 'price' in event:
            try:
                normalized['price'] = float(event['price'])
            except (ValueError, TypeError):
                normalized['price'] = event.get('price', '')
        else:
            normalized['price'] = ''
        
        normalized['message'] = str(event.get('message', ''))
        
        # Additional metadata
        if 'pair_id' in event:
            normalized['pair_id'] = str(event['pair_id'])
        
        return normalized
    
    # =================== Query History ===================
    
    def get_history(self, limit: int = 100, status: Optional[str] = None, 
                    master: Optional[str] = None, slave: Optional[str] = None) -> List[Dict]:
        """
        ดึงประวัติการคัดลอก
        
        Args:
            limit: จำนวน events สูงสุดที่ต้องการ (1-1000)
            status: กรอง status ('success' หรือ 'error')
            master: กรองด้วย master account
            slave: กรองด้วย slave account
            
        Returns:
            List[Dict]: รายการ events (เรียงจากล่าสุดไปเก่าสุด)
        """
        limit = max(1, min(limit, 1000))  # จำกัดระหว่าง 1-1000
        
        with self._lock:
            result = []
            
            for event in self.buffer:
                # Filter by status
                if status and event.get('status') != status.lower():
                    continue
                
                # Filter by master
                if master and str(event.get('master')) != str(master):
                    continue
                
                # Filter by slave
                if slave and str(event.get('slave')) != str(slave):
                    continue
                
                result.append(event)
                
                # ถึง limit แล้ว
                if len(result) >= limit:
                    break
            
            return result
    
    def get_event_by_id(self, event_id: str) -> Optional[Dict]:
        """ดึง event จาก ID"""
        with self._lock:
            for event in self.buffer:
                if event.get('id') == str(event_id):
                    return event
        return None
    
    def get_stats(self) -> Dict:
        """
        ดึงสถิติการคัดลอก
        
        Returns:
            Dict: {
                'total': int,
                'success': int,
                'error': int,
                'success_rate': float
            }
        """
        with self._lock:
            total = len(self.buffer)
            success = sum(1 for e in self.buffer if e.get('status') == 'success')
            error = sum(1 for e in self.buffer if e.get('status') == 'error')
            
            success_rate = (success / total * 100) if total > 0 else 0.0
            
            return {
                'total': total,
                'success': success,
                'error': error,
                'success_rate': round(success_rate, 2)
            }
    
    # =================== Clear History ===================
    
    def clear_history(self) -> bool:
        """
        ลบประวัติทั้งหมด
        
        Returns:
            bool: True ถ้าสำเร็จ
        """
        try:
            with self._lock:
                # ล้าง buffer
                self.buffer.clear()
                
                # ลบไฟล์
                if os.path.exists(self.history_file):
                    os.remove(self.history_file)
                
                # Broadcast clear event
                self._broadcast_to_clients({
                    'event': 'copy_history_cleared',
                    'timestamp': datetime.now().isoformat()
                })
            
            logger.info("[COPY_HISTORY] History cleared successfully")
            return True
            
        except Exception as e:
            logger.error(f"[COPY_HISTORY] Failed to clear history: {e}", exc_info=True)
            return False
    
    def clear_by_pair(self, pair_id: str) -> int:
        """
        ลบประวัติของ pair ที่ระบุ
        
        Args:
            pair_id: ID ของ Copy Pair
            
        Returns:
            int: จำนวน events ที่ลบ
        """
        try:
            with self._lock:
                # นับก่อนลบ
                original_count = len(self.buffer)
                
                # กรอง events ที่ไม่ใช่ pair นี้
                filtered = [e for e in self.buffer if e.get('pair_id') != str(pair_id)]
                
                # อัปเดต buffer
                self.buffer.clear()
                for event in filtered:
                    self.buffer.append(event)
                
                deleted_count = original_count - len(self.buffer)
                
                # เขียนไฟล์ใหม่
                if deleted_count > 0:
                    self._rewrite_history_file()
                
                logger.info(f"[COPY_HISTORY] Deleted {deleted_count} events for pair {pair_id}")
                return deleted_count
                
        except Exception as e:
            logger.error(f"[COPY_HISTORY] Failed to clear by pair: {e}", exc_info=True)
            return 0
    
    def _rewrite_history_file(self):
        """เขียนไฟล์ history ใหม่ทั้งหมด (จาก buffer)"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                for event in reversed(self.buffer):  # เขียนจากเก่าไปใหม่
                    f.write(json.dumps(event, ensure_ascii=False) + '\n')
            
            logger.debug("[COPY_HISTORY] History file rewritten")
            
        except Exception as e:
            logger.error(f"[COPY_HISTORY] Failed to rewrite history file: {e}")
    
    # =================== SSE Support ===================
    
    def add_sse_client(self, client_queue: queue.Queue):
        """
        เพิ่ม SSE client
        
        Args:
            client_queue: Queue สำหรับส่งข้อมูลไปยัง client
        """
        with self._lock:
            if client_queue not in self._clients:
                self._clients.append(client_queue)
                logger.debug(f"[COPY_HISTORY] SSE client added, total clients: {len(self._clients)}")
    
    def remove_sse_client(self, client_queue: queue.Queue):
        """
        ลบ SSE client
        
        Args:
            client_queue: Queue ที่จะลบ
        """
        with self._lock:
            if client_queue in self._clients:
                self._clients.remove(client_queue)
                logger.debug(f"[COPY_HISTORY] SSE client removed, total clients: {len(self._clients)}")
    
    def _broadcast_to_clients(self, event: Dict):
        """
        ส่งข้อมูลไปยัง SSE clients ทั้งหมด
        
        Args:
            event: Event data ที่จะส่ง
        """
        if not self._clients:
            return
        
        try:
            # สร้าง SSE message format
            payload = f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            
            dead_clients = []
            
            # ส่งไปยัง clients ทั้งหมด
            for client in self._clients:
                try:
                    client.put_nowait(payload)
                except queue.Full:
                    logger.warning("[COPY_HISTORY] Client queue full, marking for removal")
                    dead_clients.append(client)
                except Exception as e:
                    logger.warning(f"[COPY_HISTORY] Failed to send to client: {e}")
                    dead_clients.append(client)
            
            # ลบ clients ที่มีปัญหา
            for client in dead_clients:
                if client in self._clients:
                    self._clients.remove(client)
            
            if dead_clients:
                logger.debug(f"[COPY_HISTORY] Removed {len(dead_clients)} dead clients")
                
        except Exception as e:
            logger.error(f"[COPY_HISTORY] Broadcast error: {e}", exc_info=True)
    
    # =================== Utility Methods ===================
    
    def get_buffer_size(self) -> int:
        """ดึงจำนวน events ใน buffer"""
        return len(self.buffer)
    
    def get_file_size(self) -> int:
        """ดึงขนาดไฟล์ history (bytes)"""
        try:
            if os.path.exists(self.history_file):
                return os.path.getsize(self.history_file)
            return 0
        except Exception:
            return 0
    
    def get_client_count(self) -> int:
        """ดึงจำนวน SSE clients ที่เชื่อมต่ออยู่"""
        return len(self._clients)
    
    def export_history(self, output_file: str, format: str = 'json') -> bool:
        """
        Export ประวัติทั้งหมดออกเป็นไฟล์
        
        Args:
            output_file: ชื่อไฟล์ output
            format: รูปแบบ ('json' หรือ 'csv')
            
        Returns:
            bool: True ถ้าสำเร็จ
        """
        try:
            with self._lock:
                events = list(reversed(self.buffer))  # เรียงจากเก่าไปใหม่
            
            if format == 'json':
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(events, f, ensure_ascii=False, indent=2)
            
            elif format == 'csv':
                import csv
                
                with open(output_file, 'w', encoding='utf-8', newline='') as f:
                    if not events:
                        return True
                    
                    fieldnames = ['id', 'timestamp', 'status', 'master', 'slave', 
                                'action', 'symbol', 'volume', 'message']
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    
                    writer.writeheader()
                    for event in events:
                        writer.writerow({k: event.get(k, '') for k in fieldnames})
            
            else:
                logger.error(f"[COPY_HISTORY] Unsupported export format: {format}")
                return False
            
            logger.info(f"[COPY_HISTORY] Exported {len(events)} events to {output_file}")
            return True
            
        except Exception as e:
            logger.error(f"[COPY_HISTORY] Export failed: {e}", exc_info=True)
            return False
    
    def compact_history_file(self) -> bool:
        """
        บีบอัดไฟล์ history โดยเก็บเฉพาะล่าสุด max_buffer events
        
        Returns:
            bool: True ถ้าสำเร็จ
        """
        try:
            with self._lock:
                # เขียนไฟล์ใหม่จาก buffer
                self._rewrite_history_file()
            
            logger.info(f"[COPY_HISTORY] History file compacted to {len(self.buffer)} events")
            return True
            
        except Exception as e:
            logger.error(f"[COPY_HISTORY] Compact failed: {e}", exc_info=True)
            return False
    
    def __repr__(self):
        return (f"<CopyHistory buffer_size={len(self.buffer)} "
                f"clients={len(self._clients)} "
                f"file_size={self.get_file_size()} bytes>")


# =================== Helper Functions ===================

def create_copy_history_instance(max_buffer: int = 1000) -> CopyHistory:
    """
    Factory function สำหรับสร้าง CopyHistory instance
    
    Args:
        max_buffer: จำนวน events สูงสุดใน buffer
        
    Returns:
        CopyHistory: Instance ที่สร้างขึ้น
    """
    return CopyHistory(max_buffer=max_buffer)


# =================== Example Usage ===================

if __name__ == '__main__':
    # ตัวอย่างการใช้งาน
    logging.basicConfig(level=logging.DEBUG)
    
    # สร้าง instance
    history = CopyHistory(max_buffer=100)
    
    # บันทึก event
    history.record_copy_event({
        'status': 'success',
        'master': '12345',
        'slave': '67890',
        'action': 'BUY',
        'symbol': 'XAUUSD',
        'volume': 1.0,
        'message': 'Test event'
    })
    
    # ดึงประวัติ
    events = history.get_history(limit=10)
    print(f"Total events: {len(events)}")
    
    # ดึงสถิติ
    stats = history.get_stats()
    print(f"Stats: {stats}")
    
    # Export
    history.export_history('history_export.json', format='json')
    
    print(history)