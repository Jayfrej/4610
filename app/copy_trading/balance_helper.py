"""
Balance Helper for Copy Trading
ดึงข้อมูล Balance จาก MT5 Account
"""

import os
import json
import logging

logger = logging.getLogger(__name__)

class BalanceHelper:
    """Helper สำหรับดึงข้อมูล Balance"""
    
    def __init__(self, session_manager):
        self.session_manager = session_manager
    
    def get_account_balance(self, account: str) -> float:
        """
        ดึง Balance ของ Account
        
        Args:
            account: หมายเลขบัญชี
            
        Returns:
            float: Balance (หรือ 0 ถ้าหาไม่เจอ)
        """
        try:
            # ตรวจสอบว่า Account มีอยู่
            if not self.session_manager.account_exists(account):
                logger.warning(f"[BALANCE] Account {account} not found")
                return 0.0
            
            # ตรวจสอบว่า Online
            if not self.session_manager.is_instance_alive(account):
                logger.warning(f"[BALANCE] Account {account} is offline")
                return 0.0
            
            # อ่านไฟล์ balance จาก MT5 instance
            instance_path = self.session_manager.get_instance_path(account)
            balance_file = os.path.join(instance_path, "MQL5", "Files", "account_info.json")
            
            if not os.path.exists(balance_file):
                logger.warning(f"[BALANCE] Balance file not found for {account}")
                return 0.0
            
            with open(balance_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            balance = float(data.get('balance', 0))
            logger.debug(f"[BALANCE] Account {account} balance: {balance}")
            return balance
            
        except Exception as e:
            logger.error(f"[BALANCE] Failed to get balance for {account}: {e}")
            return 0.0
    
    def calculate_volume_by_risk(self, balance: float, risk_percent: float, 
                                 symbol: str, stop_loss_pips: float = 50) -> float:
        """
        คำนวณ Volume จาก Risk Percentage
        
        Args:
            balance: Balance ของ Account
            risk_percent: เปอร์เซ็นต์ Risk (เช่น 2.0 = 2%)
            symbol: Symbol ที่จะเทรด
            stop_loss_pips: ระยะ Stop Loss (pips)
            
        Returns:
            float: Volume (lots)
        """
        try:
            # คำนวณ Risk Amount
            risk_amount = balance * (risk_percent / 100)
            
            # ดึง Point Value (simplified - ควรดึงจาก MT5)
            point_values = {
                'XAUUSD': 1.0,      # Gold: $1 per 0.01 lot per $1 move
                'EURUSD': 10.0,     # Forex: $10 per 0.01 lot per pip
                'GBPUSD': 10.0,
                'USDJPY': 10.0,
            }
            
            symbol_upper = symbol.upper()
            point_value = point_values.get(symbol_upper, 10.0)  # Default: 10
            
            # คำนวณ Volume
            volume = risk_amount / (stop_loss_pips * point_value)
            
            # ปัดเศษและจำกัด Min/Max
            volume = round(volume, 2)
            volume = max(0.01, min(volume, 100.0))  # Min: 0.01, Max: 100
            
            logger.debug(
                f"[BALANCE] Calculated volume: {volume} "
                f"(Balance: {balance}, Risk: {risk_percent}%, SL: {stop_loss_pips} pips)"
            )
            
            return volume
            
        except Exception as e:
            logger.error(f"[BALANCE] Volume calculation error: {e}")
            return 0.01  # Fallback: minimum volume