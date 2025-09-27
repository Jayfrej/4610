#!/usr/bin/env python3
"""
MT5 Trading Bot Setup Script
Automated setup and configuration wizard
"""

import os
import sys
import subprocess
import shutil
import json
import secrets
from pathlib import Path
import winreg
import logging

class Colors:
    """ANSI color codes for terminal output"""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    ENDC = '\033[0m'

def print_colored(message, color=Colors.WHITE):
    """Print colored message"""
    print(f"{color}{message}{Colors.ENDC}")

def print_header(title):
    """Print section header"""
    print("\n" + "="*60)
    print_colored(f"{title.center(60)}", Colors.CYAN + Colors.BOLD)
    print("="*60)

def print_step(step_num, total_steps, description):
    """Print step information"""
    print_colored(f"\n[{step_num}/{total_steps}] {description}", Colors.YELLOW + Colors.BOLD)

def print_success(message):
    """Print success message"""
    print_colored(f"✓ {message}", Colors.GREEN)

def print_warning(message):
    """Print warning message"""
    print_colored(f"⚠ {message}", Colors.YELLOW)

def print_error(message):
    """Print error message"""
    print_colored(f"✗ {message}", Colors.RED)

class MT5TradingBotSetup:
    """Setup wizard for MT5 Trading Bot"""
    
    def __init__(self):
        self.base_dir = Path.cwd()
        self.config = {}
        self.mt5_path = None
        self.profile_source = None
        
    def run_setup(self):
        """Run complete setup process"""
        try:
            print_header("MT5 Trading Bot Setup Wizard")
            print_colored("Welcome to the MT5 Trading Bot setup wizard!", Colors.CYAN)
            print_colored("This will guide you through the installation process.", Colors.WHITE)
            
            steps = [
                "Check System Requirements",
                "Create Directory Structure", 
                "Install Python Dependencies",
                "Find MT5 Installation",
                "Configure MT5 Profile Source",
                "Generate Security Configuration",
                "Create Configuration Files",
                "Test Configuration",
                "Setup Complete"
            ]
            
            total_steps = len(steps)
            
            for i, step in enumerate(steps, 1):
                print_step(i, total_steps, step)
                
                if i == 1:
                    self.check_system_requirements()
                elif i == 2:
                    self.create_directory_structure()
                elif i == 3:
                    self.install_dependencies()
                elif i == 4:
                    self.find_mt5_installation()
                elif i == 5:
                    self.configure_profile_source()
                elif i == 6:
                    self.generate_security_config()
                elif i == 7:
                    self.create_config_files()
                elif i == 8:
                    self.test_configuration()
                elif i == 9:
                    self.setup_complete()
            
        except KeyboardInterrupt:
            print_error("\nSetup cancelled by user.")
            sys.exit(1)
        except Exception as e:
            print_error(f"Setup failed: {str(e)}")
            sys.exit(1)
    
    def check_system_requirements(self):
        """Check system requirements"""
        print("Checking system requirements...")
        
        # Check Python version
        if sys.version_info < (3, 8):
            print_error("Python 3.8+ is required")
            sys.exit(1)
        else:
            print_success(f"Python {sys.version.split()[0]} ✓")
        
        # Check if Windows
        if os.name != 'nt':
            print_warning("This bot is designed for Windows. Some features may not work on other OS.")
        else:
            print_success("Windows OS ✓")
        
        # Check required packages
        required_packages = ['flask', 'psutil', 'requests', 'python-dotenv']
        missing_packages = []
        
        for package in required_packages:
            try:
                __import__(package)
                print_success(f"{package} ✓")
            except ImportError:
                missing_packages.append(package)
                print_warning(f"{package} - will be installed")
        
        if missing_packages:
            print_colored(f"Will install missing packages: {', '.join(missing_packages)}", Colors.YELLOW)
    
    def create_directory_structure(self):
        """Create required directory structure"""
        print("Creating directory structure...")
        
        directories = [
            'app',
            'static', 
            'logs',
            'data',
            'mt5_instances',
            'backup'
        ]
        
        for directory in directories:
            dir_path = self.base_dir / directory
            if not dir_path.exists():
                dir_path.mkdir(parents=True, exist_ok=True)
                print_success(f"Created directory: {directory}")
            else:
                print_success(f"Directory exists: {directory}")
    
    def install_dependencies(self):
        """Install Python dependencies"""
        print("Installing Python dependencies...")
        
        requirements_file = self.base_dir / 'requirements.txt'
        if requirements_file.exists():
            try:
                result = subprocess.run([
                    sys.executable, '-m', 'pip', 'install', '-r', str(requirements_file)
                ], capture_output=True, text=True)
                
                if result.returncode == 0:
                    print_success("Dependencies installed successfully")
                else:
                    print_error(f"Failed to install dependencies: {result.stderr}")
                    raise Exception("Dependency installation failed")
            except Exception as e:
                print_error(f"Error installing dependencies: {str(e)}")
                raise
        else:
            print_warning("requirements.txt not found, skipping dependency installation")
    
    def find_mt5_installation(self):
        """Find MT5 installation path"""
        print("Searching for MetaTrader 5 installation...")
        
        # Common MT5 installation paths
        common_paths = [
            r"C:\Program Files\MetaTrader 5\terminal64.exe",
            r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
            r"C:\Program Files\MetaTrader 5\terminal.exe",
            r"C:\Program Files (x86)\MetaTrader 5\terminal.exe"
        ]
        
        # Check common paths
        for path in common_paths:
            if os.path.exists(path):
                self.mt5_path = path
                print_success(f"Found MT5: {path}")
                break
        
        # Try registry search
        if not self.mt5_path:
            self.mt5_path = self.find_mt5_in_registry()
        
        # Manual input if not found
        if not self.mt5_path:
            print_warning("MT5 not found automatically.")
            while True:
                user_path = input("Please enter MT5 terminal64.exe path (or 'skip'): ").strip()
                if user_path.lower() == 'skip':
                    print_warning("Skipping MT5 path configuration")
                    break
                if os.path.exists(user_path) and user_path.endswith(('.exe')):
                    self.mt5_path = user_path
                    print_success(f"MT5 path set: {user_path}")
                    break
                else:
                    print_error("Invalid path or file not found")
        
        self.config['MT5_MAIN_PATH'] = self.mt5_path or ""
    
    def find_mt5_in_registry(self):
        """Find MT5 path in Windows registry"""
        try:
            import winreg
            
            # Common registry locations for MT5
            registry_paths = [
                (winreg.HKEY_CURRENT_USER, r"Software\MetaQuotes\Terminal"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\MetaQuotes\Terminal"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\MetaQuotes\Terminal")
            ]
            
            for hkey, subkey in registry_paths:
                try:
                    with winreg.OpenKey(hkey, subkey) as key:
                        try:
                            install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                            terminal_path = os.path.join(install_path, "terminal64.exe")
                            if os.path.exists(terminal_path):
                                print_success(f"Found MT5 in registry: {terminal_path}")
                                return terminal_path
                        except FileNotFoundError:
                            continue
                except FileNotFoundError:
                    continue
            
        except ImportError:
            print_warning("Registry search not available")
        except Exception as e:
            print_warning(f"Registry search failed: {str(e)}")
        
        return None
    
    def configure_profile_source(self):
        """Configure MT5 profile source"""
        print("Configuring MT5 profile source...")
        
        # Try to find MT5 data directory automatically
        user_profile = os.path.expanduser("~")
        appdata_roaming = os.path.join(user_profile, "AppData", "Roaming")
        metaquotes_path = os.path.join(appdata_roaming, "MetaQuotes", "Terminal")
        
        profile_source = None
        
        if os.path.exists(metaquotes_path):
            # Look for terminal directories
            terminal_dirs = []
            for item in os.listdir(metaquotes_path):
                item_path = os.path.join(metaquotes_path, item)
                if os.path.isdir(item_path) and len(item) == 32:  # Terminal hash is 32 chars
                    # Check if it has required directories
                    profiles_dir = os.path.join(item_path, "profiles")
                    config_dir = os.path.join(item_path, "config")
                    if os.path.exists(profiles_dir) and os.path.exists(config_dir):
                        terminal_dirs.append(item_path)
            
            if terminal_dirs:
                if len(terminal_dirs) == 1:
                    profile_source = terminal_dirs[0]
                    print_success(f"Found MT5 data directory: {profile_source}")
                else:
                    print_colored(f"Found {len(terminal_dirs)} MT5 data directories:", Colors.YELLOW)
                    for i, dir_path in enumerate(terminal_dirs, 1):
                        print(f"  {i}. {dir_path}")
                    
                    while True:
                        try:
                            choice = input("Select directory (1-{}): ".format(len(terminal_dirs))).strip()
                            choice_idx = int(choice) - 1
                            if 0 <= choice_idx < len(terminal_dirs):
                                profile_source = terminal_dirs[choice_idx]
                                print_success(f"Selected: {profile_source}")
                                break
                            else:
                                print_error("Invalid choice")
                        except ValueError:
                            print_error("Please enter a number")
        
        # Manual input if not found
        if not profile_source:
            print_warning("MT5 data directory not found automatically.")
            print_colored("You need to:", Colors.CYAN)
            print("1. Open MT5")
            print("2. Go to File → Open Data Folder")
            print("3. Copy the path from Windows Explorer")
            
            while True:
                user_path = input("Enter MT5 data folder path (or 'skip'): ").strip()
                if user_path.lower() == 'skip':
                    print_warning("Skipping profile source configuration")
                    break
                
                if os.path.exists(user_path):
                    profiles_dir = os.path.join(user_path, "profiles")
                    config_dir = os.path.join(user_path, "config")
                    
                    if os.path.exists(profiles_dir) and os.path.exists(config_dir):
                        profile_source = user_path
                        print_success(f"Profile source set: {user_path}")
                        break
                    else:
                        print_error("Directory exists but missing 'profiles' or 'config' subdirectories")
                else:
                    print_error("Directory not found")
        
        self.profile_source = profile_source
        self.config['MT5_PROFILE_SOURCE'] = profile_source or ""
        
        # Set instances directory
        instances_dir = str(self.base_dir / 'mt5_instances')
        self.config['MT5_INSTANCES_DIR'] = instances_dir
        print_success(f"Instances directory: {instances_dir}")
    
    def generate_security_config(self):
        """Generate security configuration"""
        print("Generating security configuration...")
        
        # Generate random tokens and passwords
        self.config['SECRET_KEY'] = secrets.token_urlsafe(32)
        self.config['WEBHOOK_TOKEN'] = secrets.token_urlsafe(16)
        
        print_success(f"Generated secret key: {self.config['SECRET_KEY'][:8]}...")
        print_success(f"Generated webhook token: {self.config['WEBHOOK_TOKEN']}")
        
        # Basic auth credentials
        print_colored("\nSetup web interface credentials:", Colors.CYAN)
        
        username = input("Admin username (default: admin): ").strip()
        self.config['BASIC_USER'] = username or 'admin'
        
        while True:
            password = input("Admin password (min 6 chars): ").strip()
            if len(password) >= 6:
                self.config['BASIC_PASS'] = password
                break
            else:
                print_error("Password must be at least 6 characters")
        
        print_success("Admin credentials configured")
        
        # External URL
        print_colored("\nExternal URL configuration:", Colors.CYAN)
        print("This is the URL that TradingView will use to send webhooks.")
        print("Examples: https://yourdomain.com, https://subdomain.example.com")
        
        external_url = input("External base URL (default: http://localhost:5000): ").strip()
        self.config['EXTERNAL_BASE_URL'] = external_url or 'http://localhost:5000'
        
        print_success(f"External URL: {self.config['EXTERNAL_BASE_URL']}")
        
        # Email configuration (optional)
        print_colored("\nEmail notifications (optional):", Colors.CYAN)
        enable_email = input("Enable email notifications? (y/N): ").strip().lower()
        
        if enable_email == 'y':
            self.config['EMAIL_ENABLED'] = 'True'
            self.config['SMTP_SERVER'] = input("SMTP server (default: smtp.gmail.com): ").strip() or 'smtp.gmail.com'
            self.config['SMTP_PORT'] = input("SMTP port (default: 587): ").strip() or '587'
            self.config['SMTP_USER'] = input("SMTP username/email: ").strip()
            self.config['SMTP_PASS'] = input("SMTP password/app password: ").strip()
            self.config['FROM_EMAIL'] = input("From email (default: same as SMTP user): ").strip() or self.config['SMTP_USER']
            self.config['TO_EMAILS'] = input("Alert recipients (comma-separated): ").strip()
            print_success("Email configuration completed")
        else:
            self.config['EMAIL_ENABLED'] = 'False'
            print_success("Email notifications disabled")
    
    def create_config_files(self):
        """Create configuration files"""
        print("Creating configuration files...")
        
        # Create .env file
        env_content = []
        env_content.append("# MT5 Trading Bot Configuration")
        env_content.append("# Generated by setup wizard")
        env_content.append("")
        
        env_content.append("# Basic Authentication")
        env_content.append(f"BASIC_USER={self.config.get('BASIC_USER', 'admin')}")
        env_content.append(f"BASIC_PASS={self.config.get('BASIC_PASS', 'admin')}")
        env_content.append("")
        
        env_content.append("# Security")
        env_content.append(f"SECRET_KEY={self.config.get('SECRET_KEY', '')}")
        env_content.append(f"WEBHOOK_TOKEN={self.config.get('WEBHOOK_TOKEN', '')}")
        env_content.append(f"EXTERNAL_BASE_URL={self.config.get('EXTERNAL_BASE_URL', 'http://localhost:5000')}")
        env_content.append("")
        
        env_content.append("# Server")
        env_content.append("PORT=5000")
        env_content.append("DEBUG=False")
        env_content.append("")
        
        env_content.append("# MT5 Configuration")
        env_content.append(f"MT5_MAIN_PATH={self.config.get('MT5_MAIN_PATH', '')}")
        env_content.append(f"MT5_INSTANCES_DIR={self.config.get('MT5_INSTANCES_DIR', '')}")
        env_content.append(f"MT5_PROFILE_SOURCE={self.config.get('MT5_PROFILE_SOURCE', '')}")
        env_content.append("DELETE_INSTANCE_FILES=False")
        env_content.append("TRADING_METHOD=file")
        env_content.append("")
        
        env_content.append("# Email Notifications")
        env_content.append(f"EMAIL_ENABLED={self.config.get('EMAIL_ENABLED', 'False')}")
        if self.config.get('EMAIL_ENABLED') == 'True':
            env_content.append(f"SMTP_SERVER={self.config.get('SMTP_SERVER', 'smtp.gmail.com')}")
            env_content.append(f"SMTP_PORT={self.config.get('SMTP_PORT', '587')}")
            env_content.append(f"SMTP_USER={self.config.get('SMTP_USER', '')}")
            env_content.append(f"SMTP_PASS={self.config.get('SMTP_PASS', '')}")
            env_content.append(f"FROM_EMAIL={self.config.get('FROM_EMAIL', '')}")
            env_content.append(f"TO_EMAILS={self.config.get('TO_EMAILS', '')}")
        env_content.append("")
        
        env_content.append("# Symbol Mapping")
        env_content.append("SYMBOL_FETCH_ENABLED=False")
        env_content.append("FUZZY_MATCH_THRESHOLD=0.6")
        env_content.append("")
        
        env_content.append("# Rate Limiting")
        env_content.append("RATE_LIMIT_WEBHOOK=10 per minute")
        env_content.append("RATE_LIMIT_API=100 per hour")
        
        # Write .env file
        env_file = self.base_dir / '.env'
        with open(env_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(env_content))
        
        print_success("Created .env configuration file")
        
        # Create startup script
        self.create_startup_script()
        
        # Set file permissions (Windows)
        try:
            import stat
            os.chmod(env_file, stat.S_IREAD | stat.S_IWRITE)
            print_success("Set secure file permissions on .env")
        except:
            print_warning("Could not set file permissions")
    
    def create_startup_script(self):
        """Create startup scripts"""
        print("Creating startup scripts...")
        
        # Windows batch script
        bat_content = [
            "@echo off",
            "title MT5 Trading Bot",
            "cd /d \"%~dp0\"",
            "",
            "echo Starting MT5 Trading Bot...",
            "echo.",
            "",
            "REM Activate virtual environment if it exists",
            "if exist \"venv\\Scripts\\activate.bat\" (",
            "    call venv\\Scripts\\activate.bat",
            "    echo Virtual environment activated",
            ")",
            "",
            "REM Start the server", 
            "python server.py",
            "",
            "pause"
        ]
        
        bat_file = self.base_dir / 'start.bat'
        with open(bat_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(bat_content))
        
        print_success("Created start.bat startup script")
        
        # Python startup script
        py_content = [
            "#!/usr/bin/env python3",
            '"""MT5 Trading Bot Startup Script"""',
            "",
            "import os",
            "import sys",
            "import subprocess",
            "from pathlib import Path",
            "",
            "def main():",
            "    # Change to script directory",
            "    script_dir = Path(__file__).parent",
            "    os.chdir(script_dir)",
            "",
            "    # Check if .env exists",
            "    if not (script_dir / '.env').exists():",
            "        print('Configuration file .env not found!')",
            "        print('Please run setup.py first.')",
            "        sys.exit(1)",
            "",
            "    # Start server",
            "    try:",
            "        import server",
            "        # This will import and run the Flask app",
            "    except ImportError as e:",
            "        print(f'Failed to import server: {e}')",
            "        print('Please install dependencies: pip install -r requirements.txt')",
            "        sys.exit(1)",
            "    except Exception as e:",
            "        print(f'Server error: {e}')",
            "        sys.exit(1)",
            "",
            "if __name__ == '__main__':",
            "    main()"
        ]
        
        py_file = self.base_dir / 'start.py'
        with open(py_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(py_content))
        
        print_success("Created start.py startup script")
    
    def test_configuration(self):
        """Test the configuration"""
        print("Testing configuration...")
        
        # Test MT5 path
        if self.config.get('MT5_MAIN_PATH'):
            if os.path.exists(self.config['MT5_MAIN_PATH']):
                print_success("MT5 executable found")
            else:
                print_warning("MT5 executable not found")
        else:
            print_warning("MT5 path not configured")
        
        # Test profile source
        if self.config.get('MT5_PROFILE_SOURCE'):
            if os.path.exists(self.config['MT5_PROFILE_SOURCE']):
                profiles_dir = os.path.join(self.config['MT5_PROFILE_SOURCE'], 'profiles')
                config_dir = os.path.join(self.config['MT5_PROFILE_SOURCE'], 'config')
                
                if os.path.exists(profiles_dir) and os.path.exists(config_dir):
                    print_success("MT5 profile source valid")
                else:
                    print_warning("MT5 profile source missing required directories")
            else:
                print_warning("MT5 profile source not found")
        else:
            print_warning("MT5 profile source not configured")
        
        # Test instances directory
        instances_dir = self.config.get('MT5_INSTANCES_DIR')
        if instances_dir:
            Path(instances_dir).mkdir(parents=True, exist_ok=True)
            if os.path.exists(instances_dir) and os.access(instances_dir, os.W_OK):
                print_success("Instances directory accessible")
            else:
                print_warning("Instances directory not accessible")
        
        # Test webhook URL
        webhook_url = f"{self.config.get('EXTERNAL_BASE_URL', '')}/webhook/{self.config.get('WEBHOOK_TOKEN', '')}"
        print_success(f"Webhook URL: {webhook_url}")
    
    def setup_complete(self):
        """Setup completion"""
        print_header("Setup Complete!")
        
        print_colored("🎉 MT5 Trading Bot setup completed successfully!", Colors.GREEN + Colors.BOLD)
        print()
        
        print_colored("Next steps:", Colors.CYAN + Colors.BOLD)
        print("1. Prepare your MT5 Default profile:")
        print("   - Open MT5 and configure charts, EAs, and themes as desired")
        print("   - Save profile as 'Default': File → Profiles → Save As... → Default")
        print()
        
        print("2. Start the bot:")
        print("   - Double-click 'start.bat' or run 'python server.py'")
        print("   - Access web interface at http://localhost:5000")
        print(f"   - Login: {self.config.get('BASIC_USER')} / {self.config.get('BASIC_PASS')}")
        print()
        
        print("3. Configure TradingView webhook:")
        webhook_url = f"{self.config.get('EXTERNAL_BASE_URL')}/webhook/{self.config.get('WEBHOOK_TOKEN')}"
        print(f"   - Webhook URL: {webhook_url}")
        print()
        
        print("4. For external access, setup Cloudflare Tunnel:")
        print("   - Install cloudflared")
        print("   - Run: cloudflared tunnel --url http://localhost:5000")
        print()
        
        print_colored("Configuration files created:", Colors.YELLOW)
        print("✓ .env - Main configuration")
        print("✓ start.bat - Windows startup script")
        print("✓ start.py - Python startup script")
        print()
        
        print_colored("Happy trading! 🚀", Colors.GREEN + Colors.BOLD)

def main():
    """Main setup function"""
    if len(sys.argv) > 1 and sys.argv[1] == '--help':
        print("MT5 Trading Bot Setup Script")
        print("Usage: python setup.py")
        print()
        print("This script will guide you through setting up the MT5 Trading Bot.")
        return
    
    # Check if already configured
    env_file = Path('.env')
    if env_file.exists():
        print_colored("Configuration file already exists!", Colors.YELLOW)
        overwrite = input("Overwrite existing configuration? (y/N): ").strip().lower()
        if overwrite != 'y':
            print("Setup cancelled.")
            return
    
    # Run setup
    setup = MT5TradingBotSetup()
    setup.run_setup()

if __name__ == '__main__':
    main()