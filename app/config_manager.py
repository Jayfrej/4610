import os
import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
import secrets

logger = logging.getLogger(__name__)

@dataclass
class ServerConfig:
    """Server configuration settings"""
    host: str = "0.0.0.0"
    port: int = 5000
    debug: bool = False
    secret_key: str = ""
    basic_user: str = "admin"
    basic_pass: str = "admin"

@dataclass
class WebhookConfig:
    """Webhook configuration settings"""
    token: str = ""
    external_base_url: str = "http://localhost:5000"
    rate_limit: str = "10 per minute"

@dataclass
class MT5Config:
    """MT5 configuration settings"""
    main_path: str = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    instances_dir: str = r"C:\trading_bot\mt5_instances"
    profile_source: str = r"C:\Users\{}\AppData\Roaming\MetaQuotes\Terminal\XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
    delete_instance_files: bool = False
    trading_method: str = "file"  # "file" or "direct"

@dataclass
class EmailConfig:
    """Email notification configuration"""
    enabled: bool = False
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    from_email: str = ""
    to_emails: list = None
    
    def __post_init__(self):
        if self.to_emails is None:
            self.to_emails = []

@dataclass
class SymbolConfig:
    """Symbol mapping configuration"""
    fetch_enabled: bool = False
    fuzzy_match_threshold: float = 0.6
    cache_expiry: int = 3600
    auto_update_whitelist: bool = True

@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    max_bytes: int = 10485760  # 10MB
    backup_count: int = 5
    format: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

class ConfigManager:
    """Manage application configuration"""
    
    def __init__(self, env_file: str = ".env"):
        self.env_file = env_file
        self.config_file = "config.json"
        
        # Initialize configuration objects
        self.server = ServerConfig()
        self.webhook = WebhookConfig()
        self.mt5 = MT5Config()
        self.email = EmailConfig()
        self.symbol = SymbolConfig()
        self.logging = LoggingConfig()
        
        # Load configuration
        self.load_config()
        
        logger.info("[CONFIG] Configuration manager initialized")
    
    def load_config(self):
        """Load configuration from .env and config.json"""
        # Load from .env file first
        self._load_from_env()
        
        # Load from JSON config file (overrides .env)
        self._load_from_json()
        
        # Validate and fix configuration
        self._validate_config()
        
        logger.info("[CONFIG] Configuration loaded successfully")
    
    def _load_from_env(self):
        """Load configuration from .env file"""
        if not os.path.exists(self.env_file):
            logger.warning(f"[CONFIG] .env file not found: {self.env_file}")
            return
        
        try:
            from dotenv import load_dotenv
            load_dotenv(self.env_file)
            
            # Server config
            self.server.host = os.getenv('HOST', self.server.host)
            self.server.port = int(os.getenv('PORT', self.server.port))
            self.server.debug = os.getenv('DEBUG', 'False').lower() == 'true'
            self.server.secret_key = os.getenv('SECRET_KEY', self.server.secret_key)
            self.server.basic_user = os.getenv('BASIC_USER', self.server.basic_user)
            self.server.basic_pass = os.getenv('BASIC_PASS', self.server.basic_pass)
            
            # Webhook config
            self.webhook.token = os.getenv('WEBHOOK_TOKEN', self.webhook.token)
            self.webhook.external_base_url = os.getenv('EXTERNAL_BASE_URL', self.webhook.external_base_url)
            self.webhook.rate_limit = os.getenv('RATE_LIMIT_WEBHOOK', self.webhook.rate_limit)
            
            # MT5 config
            self.mt5.main_path = os.getenv('MT5_MAIN_PATH', self.mt5.main_path)
            self.mt5.instances_dir = os.getenv('MT5_INSTANCES_DIR', self.mt5.instances_dir)
            self.mt5.profile_source = os.getenv('MT5_PROFILE_SOURCE', self.mt5.profile_source)
            self.mt5.delete_instance_files = os.getenv('DELETE_INSTANCE_FILES', 'False').lower() == 'true'
            self.mt5.trading_method = os.getenv('TRADING_METHOD', self.mt5.trading_method)
            
            # Email config
            self.email.enabled = os.getenv('EMAIL_ENABLED', 'False').lower() == 'true'
            self.email.smtp_server = os.getenv('SMTP_SERVER', self.email.smtp_server)
            self.email.smtp_port = int(os.getenv('SMTP_PORT', self.email.smtp_port))
            self.email.smtp_user = os.getenv('SMTP_USER', self.email.smtp_user)
            self.email.smtp_pass = os.getenv('SMTP_PASS', self.email.smtp_pass)
            self.email.from_email = os.getenv('FROM_EMAIL', self.email.smtp_user)
            
            to_emails_str = os.getenv('TO_EMAILS', '')
            if to_emails_str:
                self.email.to_emails = [email.strip() for email in to_emails_str.split(',') if email.strip()]
            
            # Symbol config
            self.symbol.fetch_enabled = os.getenv('SYMBOL_FETCH_ENABLED', 'False').lower() == 'true'
            self.symbol.fuzzy_match_threshold = float(os.getenv('FUZZY_MATCH_THRESHOLD', self.symbol.fuzzy_match_threshold))
            self.symbol.cache_expiry = int(os.getenv('SYMBOL_CACHE_EXPIRY', self.symbol.cache_expiry))
            self.symbol.auto_update_whitelist = os.getenv('AUTO_UPDATE_WHITELIST', 'True').lower() == 'true'
            
            # Logging config
            self.logging.level = os.getenv('LOG_LEVEL', self.logging.level).upper()
            self.logging.max_bytes = int(os.getenv('LOG_MAX_BYTES', self.logging.max_bytes))
            self.logging.backup_count = int(os.getenv('LOG_BACKUP_COUNT', self.logging.backup_count))
            
            logger.info("[CONFIG] Loaded configuration from .env file")
            
        except Exception as e:
            logger.error(f"[CONFIG] Failed to load .env file: {str(e)}")
    
    def _load_from_json(self):
        """Load configuration from JSON file"""
        if not os.path.exists(self.config_file):
            return
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Update configuration objects
            if 'server' in data:
                for key, value in data['server'].items():
                    if hasattr(self.server, key):
                        setattr(self.server, key, value)
            
            if 'webhook' in data:
                for key, value in data['webhook'].items():
                    if hasattr(self.webhook, key):
                        setattr(self.webhook, key, value)
            
            if 'mt5' in data:
                for key, value in data['mt5'].items():
                    if hasattr(self.mt5, key):
                        setattr(self.mt5, key, value)
            
            if 'email' in data:
                for key, value in data['email'].items():
                    if hasattr(self.email, key):
                        setattr(self.email, key, value)
            
            if 'symbol' in data:
                for key, value in data['symbol'].items():
                    if hasattr(self.symbol, key):
                        setattr(self.symbol, key, value)
            
            if 'logging' in data:
                for key, value in data['logging'].items():
                    if hasattr(self.logging, key):
                        setattr(self.logging, key, value)
            
            logger.info("[CONFIG] Loaded configuration from JSON file")
            
        except Exception as e:
            logger.error(f"[CONFIG] Failed to load JSON config: {str(e)}")
    
    def _validate_config(self):
        """Validate and fix configuration"""
        # Generate secret key if not set
        if not self.server.secret_key:
            self.server.secret_key = secrets.token_urlsafe(32)
            logger.info("[CONFIG] Generated new secret key")
        
        # Generate webhook token if not set
        if not self.webhook.token:
            self.webhook.token = secrets.token_urlsafe(16)
            logger.warning("[CONFIG] Generated new webhook token - update your alerts!")
        
        # Expand environment variables in paths
        self.mt5.instances_dir = os.path.expandvars(self.mt5.instances_dir)
        self.mt5.profile_source = os.path.expandvars(self.mt5.profile_source)
        
        # Validate MT5 paths
        if not os.path.exists(self.mt5.main_path):
            logger.warning(f"[CONFIG] MT5 executable not found: {self.mt5.main_path}")
        
        if not os.path.exists(self.mt5.profile_source):
            logger.warning(f"[CONFIG] MT5 profile source not found: {self.mt5.profile_source}")
        
        # Validate email config
        if self.email.enabled:
            if not self.email.smtp_user or not self.email.smtp_pass:
                logger.warning("[CONFIG] Email enabled but credentials missing")
                self.email.enabled = False
            
            if not self.email.to_emails:
                logger.warning("[CONFIG] Email enabled but no recipients configured")
                self.email.enabled = False
        
        # Validate external base URL
        if self.webhook.external_base_url.endswith('/'):
            self.webhook.external_base_url = self.webhook.external_base_url.rstrip('/')
            logger.info("[CONFIG] Removed trailing slash from external base URL")
        
        # Validate fuzzy match threshold
        if not 0.0 <= self.symbol.fuzzy_match_threshold <= 1.0:
            self.symbol.fuzzy_match_threshold = 0.6
            logger.warning("[CONFIG] Invalid fuzzy match threshold, reset to 0.6")
    
    def save_config(self):
        """Save current configuration to JSON file"""
        try:
            config_data = {
                'server': asdict(self.server),
                'webhook': asdict(self.webhook),
                'mt5': asdict(self.mt5),
                'email': asdict(self.email),
                'symbol': asdict(self.symbol),
                'logging': asdict(self.logging)
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[CONFIG] Configuration saved to {self.config_file}")
            
        except Exception as e:
            logger.error(f"[CONFIG] Failed to save configuration: {str(e)}")
    
    def get_webhook_url(self) -> str:
        """Get complete webhook URL"""
        return f"{self.webhook.external_base_url}/webhook/{self.webhook.token}"
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get configuration summary for display"""
        return {
            'server': {
                'host': self.server.host,
                'port': self.server.port,
                'debug': self.server.debug
            },
            'webhook': {
                'token_length': len(self.webhook.token),
                'external_url': self.webhook.external_base_url,
                'rate_limit': self.webhook.rate_limit
            },
            'mt5': {
                'executable_exists': os.path.exists(self.mt5.main_path),
                'profile_source_exists': os.path.exists(self.mt5.profile_source),
                'instances_dir': self.mt5.instances_dir,
                'trading_method': self.mt5.trading_method
            },
            'email': {
                'enabled': self.email.enabled,
                'smtp_server': self.email.smtp_server,
                'recipients_count': len(self.email.to_emails)
            },
            'symbol': {
                'fetch_enabled': self.symbol.fetch_enabled,
                'fuzzy_threshold': self.symbol.fuzzy_match_threshold,
                'auto_update': self.symbol.auto_update_whitelist
            }
        }
    
    def update_webhook_token(self) -> str:
        """Generate new webhook token"""
        old_token = self.webhook.token
        self.webhook.token = secrets.token_urlsafe(16)
        
        logger.warning(f"[CONFIG] Webhook token updated: {old_token[:4]}... → {self.webhook.token[:4]}...")
        return self.webhook.token
    
    def validate_mt5_setup(self) -> Dict[str, Any]:
        """Validate MT5 setup and return status"""
        status = {
            'executable': {
                'path': self.mt5.main_path,
                'exists': os.path.exists(self.mt5.main_path),
                'readable': False
            },
            'profile_source': {
                'path': self.mt5.profile_source,
                'exists': os.path.exists(self.mt5.profile_source),
                'has_profiles': False,
                'has_config': False
            },
            'instances_dir': {
                'path': self.mt5.instances_dir,
                'exists': os.path.exists(self.mt5.instances_dir),
                'writable': False
            }
        }
        
        # Check executable
        if status['executable']['exists']:
            try:
                status['executable']['readable'] = os.access(self.mt5.main_path, os.R_OK)
            except:
                pass
        
        # Check profile source
        if status['profile_source']['exists']:
            profiles_dir = os.path.join(self.mt5.profile_source, 'profiles')
            config_dir = os.path.join(self.mt5.profile_source, 'config')
            
            status['profile_source']['has_profiles'] = os.path.exists(profiles_dir)
            status['profile_source']['has_config'] = os.path.exists(config_dir)
        
        # Check instances directory
        if status['instances_dir']['exists']:
            try:
                status['instances_dir']['writable'] = os.access(self.mt5.instances_dir, os.W_OK)
            except:
                pass
        else:
            # Try to create it
            try:
                os.makedirs(self.mt5.instances_dir, exist_ok=True)
                status['instances_dir']['exists'] = True
                status['instances_dir']['writable'] = True
            except Exception as e:
                logger.error(f"[CONFIG] Cannot create instances directory: {str(e)}")
        
        return status
    
    def export_config(self, filename: str = None) -> str:
        """Export configuration to file"""
        if filename is None:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"config_backup_{timestamp}.json"
        
        try:
            config_data = {
                'version': '1.0',
                'exported_at': datetime.now().isoformat(),
                'config': {
                    'server': asdict(self.server),
                    'webhook': asdict(self.webhook),
                    'mt5': asdict(self.mt5),
                    'email': asdict(self.email),
                    'symbol': asdict(self.symbol),
                    'logging': asdict(self.logging)
                }
            }
            
            # Remove sensitive data
            config_data['config']['server']['secret_key'] = '***HIDDEN***'
            config_data['config']['server']['basic_pass'] = '***HIDDEN***'
            config_data['config']['webhook']['token'] = '***HIDDEN***'
            config_data['config']['email']['smtp_pass'] = '***HIDDEN***'
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"[CONFIG] Configuration exported to {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"[CONFIG] Failed to export configuration: {str(e)}")
            raise

# Global configuration instance
config = ConfigManager()