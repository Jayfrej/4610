"""
Copy Trading Module
Handles Master-Slave account copy trading functionality
"""

__version__ = "1.0.0"
__author__ = "MT5 Trading Bot"

from .copy_manager import CopyManager
from .copy_handler import CopyHandler
from .copy_executor import CopyExecutor
from .copy_history import CopyHistory
from .balance_helper import BalanceHelper  

__all__ = [
    'CopyManager',
    'CopyHandler',
    'CopyExecutor',
    'CopyHistory',
    'BalanceHelper'  
]