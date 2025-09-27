import os
import re
import json
import logging
from typing import Dict, List, Optional
from difflib import SequenceMatcher
import requests

logger = logging.getLogger(__name__)

class SymbolMapper:
    """Auto symbol mapping with fuzzy matching"""
    
    def __init__(self):
        self.mapping_cache = {}
        self.base_mappings = {}
        self.custom_mappings = {}
        self.symbol_whitelist = set()
        
        # Load base mappings from reference repo
        self._load_base_mappings()
        
        # Load custom user mappings
        self._load_custom_mappings()
        
        logger.info("[SYMBOL_MAPPER] Initialized successfully")
        logger.info(f"[SYMBOL_MAPPER] Loaded {len(self.base_mappings)} base mappings")
        logger.info(f"[SYMBOL_MAPPER] Loaded {len(self.custom_mappings)} custom mappings")
    
    def _load_base_mappings(self):
        """Load base symbol mappings from reference repo (4607)"""
        try:
            # Try to load from local file first
            mappings_file = 'data/symbol_mappings.json'
            if os.path.exists(mappings_file):
                with open(mappings_file, 'r', encoding='utf-8') as f:
                    self.base_mappings = json.load(f)
                logger.info(f"[SYMBOL_MAPPER] Loaded base mappings from local file: {mappings_file}")
                return
            
            # If local file doesn't exist, create basic mappings
            self.base_mappings = self._create_basic_mappings()
            
            # Save to file for future use
            os.makedirs('data', exist_ok=True)
            with open(mappings_file, 'w', encoding='utf-8') as f:
                json.dump(self.base_mappings, f, indent=2, ensure_ascii=False)
            
            logger.info("[SYMBOL_MAPPER] Created and saved basic symbol mappings")
            
        except Exception as e:
            logger.error(f"[SYMBOL_MAPPER] Failed to load base mappings: {str(e)}")
            self.base_mappings = self._create_basic_mappings()
    
    def _create_basic_mappings(self) -> Dict[str, str]:
        """Create basic symbol mappings"""
        return {
            # Forex majors
            'eurusd': 'EURUSD',
            'gbpusd': 'GBPUSD', 
            'usdjpy': 'USDJPY',
            'usdchf': 'USDCHF',
            'usdcad': 'USDCAD',
            'audusd': 'AUDUSD',
            'nzdusd': 'NZDUSD',
            
            # Gold/Silver
            'xauusd': 'XAUUSD',
            'xauusdm': 'XAUUSD',
            'gold': 'XAUUSD',
            'xagusd': 'XAGUSD',
            'silver': 'XAGUSD',
            
            # Oil
            'usoil': 'USOIL',
            'ukoil': 'UKOIL',
            'wti': 'USOIL',
            'brent': 'UKOIL',
            
            # Crypto
            'btcusd': 'BTCUSD',
            'ethusd': 'ETHUSD',
            'bitcoin': 'BTCUSD',
            'ethereum': 'ETHUSD',
            
            # Indices
            'us30': 'US30',
            'us500': 'US500',
            'nas100': 'NAS100',
            'ger30': 'GER30',
            'uk100': 'UK100',
            'jp225': 'JP225',
            'aus200': 'AUS200',
            
            # Common suffixes/prefixes removal
            'eurusd.': 'EURUSD',
            'eurusd.m': 'EURUSD',
            'eurusdm': 'EURUSD',
            'm_eurusd': 'EURUSD',
            'forex_eurusd': 'EURUSD'
        }
    
    def _load_custom_mappings(self):
        """Load custom user-defined mappings"""
        try:
            custom_file = 'data/custom_mappings.json'
            if os.path.exists(custom_file):
                with open(custom_file, 'r', encoding='utf-8') as f:
                    self.custom_mappings = json.load(f)
                logger.info(f"[SYMBOL_MAPPER] Loaded {len(self.custom_mappings)} custom mappings")
        except Exception as e:
            logger.error(f"[SYMBOL_MAPPER] Failed to load custom mappings: {str(e)}")
            self.custom_mappings = {}
    
    def add_custom_mapping(self, source: str, target: str):
        """Add custom symbol mapping"""
        try:
            normalized_source = self._normalize_symbol(source)
            self.custom_mappings[normalized_source] = target
            
            # Save to file
            custom_file = 'data/custom_mappings.json'
            os.makedirs('data', exist_ok=True)
            with open(custom_file, 'w', encoding='utf-8') as f:
                json.dump(self.custom_mappings, f, indent=2, ensure_ascii=False)
            
            # Clear cache to force remapping
            self.mapping_cache.clear()
            
            logger.info(f"[SYMBOL_MAPPER] Added custom mapping: {source} -> {target}")
            
        except Exception as e:
            logger.error(f"[SYMBOL_MAPPER] Failed to add custom mapping: {str(e)}")
    
    def set_symbol_whitelist(self, symbols: List[str]):
        """Set whitelist of valid symbols (from MT5 Market Watch)"""
        self.symbol_whitelist = set(symbol.upper() for symbol in symbols)
        logger.info(f"[SYMBOL_MAPPER] Updated whitelist with {len(self.symbol_whitelist)} symbols")
    
    def map_symbol(self, original_symbol: str) -> Optional[str]:
        """Map symbol with auto-mapping logic"""
        if not original_symbol:
            return None
        
        # Check cache first
        if original_symbol in self.mapping_cache:
            return self.mapping_cache[original_symbol]
        
        # Normalize input symbol
        normalized = self._normalize_symbol(original_symbol)
        
        # 1. Try exact match in custom mappings (highest priority)
        if normalized in self.custom_mappings:
            result = self.custom_mappings[normalized]
            self.mapping_cache[original_symbol] = result
            logger.debug(f"[SYMBOL_MAPPER] Custom exact match: {original_symbol} -> {result}")
            return result
        
        # 2. Try exact match in base mappings
        if normalized in self.base_mappings:
            result = self.base_mappings[normalized]
            # Validate against whitelist if available
            if not self.symbol_whitelist or result in self.symbol_whitelist:
                self.mapping_cache[original_symbol] = result
                logger.debug(f"[SYMBOL_MAPPER] Base exact match: {original_symbol} -> {result}")
                return result
        
        # 3. Try fuzzy matching against whitelist (if available)
        if self.symbol_whitelist:
            fuzzy_result = self._fuzzy_match(normalized, list(self.symbol_whitelist))
            if fuzzy_result:
                self.mapping_cache[original_symbol] = fuzzy_result
                logger.debug(f"[SYMBOL_MAPPER] Fuzzy match: {original_symbol} -> {fuzzy_result}")
                return fuzzy_result
        
        # 4. Try fuzzy matching against all mapping targets
        all_targets = set(self.base_mappings.values()) | set(self.custom_mappings.values())
        fuzzy_result = self._fuzzy_match(normalized, list(all_targets))
        if fuzzy_result:
            # Validate against whitelist if available
            if not self.symbol_whitelist or fuzzy_result in self.symbol_whitelist:
                self.mapping_cache[original_symbol] = fuzzy_result
                logger.debug(f"[SYMBOL_MAPPER] Fuzzy match (targets): {original_symbol} -> {fuzzy_result}")
                return fuzzy_result
        
        # 5. Try direct use of normalized symbol (if valid)
        if not self.symbol_whitelist or normalized.upper() in self.symbol_whitelist:
            result = normalized.upper()
            self.mapping_cache[original_symbol] = result
            logger.debug(f"[SYMBOL_MAPPER] Direct use: {original_symbol} -> {result}")
            return result
        
        # 6. No mapping found
        logger.warning(f"[SYMBOL_MAPPER] No mapping found for: {original_symbol}")
        return None
    
    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol by cleaning common patterns"""
        if not symbol:
            return ""
        
        # Convert to lowercase and remove spaces
        normalized = symbol.strip().lower()
        
        # Remove common suffixes
        suffixes_to_remove = [
            '.m', '.', '_m', 'm', '_mini', '.mini', '_micro', '.micro',
            '.cash', '_cash', '.spot', '_spot', '_fx', '.fx'
        ]
        
        for suffix in suffixes_to_remove:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)]
                break
        
        # Remove common prefixes
        prefixes_to_remove = ['m_', 'mini_', 'micro_', 'fx_', 'forex_', 'cfd_']
        
        for prefix in prefixes_to_remove:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
                break
        
        # Remove special characters and numbers at the end
        normalized = re.sub(r'[^a-zA-Z0-9]', '', normalized)
        normalized = re.sub(r'\d+$', '', normalized)  # Remove trailing numbers
        
        return normalized
    
    def _fuzzy_match(self, target: str, candidates: List[str], threshold: float = 0.6) -> Optional[str]:
        """Find best fuzzy match from candidates"""
        if not target or not candidates:
            return None
        
        best_match = None
        best_score = 0
        
        target_normalized = self._normalize_symbol(target)
        
        for candidate in candidates:
            candidate_normalized = self._normalize_symbol(candidate)
            
            # Calculate similarity
            score = SequenceMatcher(None, target_normalized, candidate_normalized).ratio()
            
            # Also check if target is contained in candidate or vice versa
            if target_normalized in candidate_normalized or candidate_normalized in target_normalized:
                score = max(score, 0.8)
            
            if score > best_score and score >= threshold:
                best_score = score
                best_match = candidate
        
        if best_match:
            logger.debug(f"[SYMBOL_MAPPER] Fuzzy match: {target} -> {best_match} (score: {best_score:.2f})")
        
        return best_match
    
    def get_mapping_stats(self) -> Dict:
        """Get mapping statistics"""
        return {
            'base_mappings': len(self.base_mappings),
            'custom_mappings': len(self.custom_mappings),
            'cached_mappings': len(self.mapping_cache),
            'whitelist_size': len(self.symbol_whitelist)
        }
    
    def clear_cache(self):
        """Clear mapping cache"""
        self.mapping_cache.clear()
        logger.info("[SYMBOL_MAPPER] Cache cleared")
    
    def export_mappings(self, filename: str):
        """Export all mappings to file"""
        try:
            all_mappings = {
                'base_mappings': self.base_mappings,
                'custom_mappings': self.custom_mappings,
                'cache': self.mapping_cache,
                'whitelist': list(self.symbol_whitelist)
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(all_mappings, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[SYMBOL_MAPPER] Exported mappings to {filename}")
            
        except Exception as e:
            logger.error(f"[SYMBOL_MAPPER] Failed to export mappings: {str(e)}")
    
    def test_mapping(self, test_symbols: List[str]) -> Dict:
        """Test mapping for a list of symbols"""
        results = {}
        for symbol in test_symbols:
            mapped = self.map_symbol(symbol)
            results[symbol] = {
                'mapped': mapped,
                'success': mapped is not None
            }
        return results