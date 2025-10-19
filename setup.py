import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import sys
import os
import threading
from pathlib import Path

class SetupWizard:
    def __init__(self, root):
        self.root = root
        self.root.title("TradingView to MT5 - Setup Wizard")
        self.root.geometry("700x600")
        self.root.resizable(True, True)
        
        self.base_dir = Path.cwd()
        
        # Configure dark theme colors
        self.bg_dark = "#1e1e1e"
        self.bg_secondary = "#2d2d2d"
        self.bg_input = "#3c3c3c"
        self.fg_primary = "#ffffff"
        self.fg_secondary = "#b0b0b0"
        self.accent_blue = "#0078d4"
        self.accent_green = "#107c10"
        self.accent_red = "#d13438"
        self.accent_yellow = "#ffa500"
        
        # Apply dark theme
        self.setup_dark_theme()
        
        # Variables
        self.basic_user = tk.StringVar(value="admin")
        self.basic_password = tk.StringVar()
        self.external_base_url = tk.StringVar(value="http://localhost:5000")
        self.mt5_main_path = tk.StringVar()
        self.mt5_instances_dir = tk.StringVar()
        
        # Auto-set instances directory
        self.mt5_instances_dir.set(str(self.base_dir / 'mt5_instances'))
        
        self.setup_ui()
        
    def setup_dark_theme(self):
        """Setup dark theme for the application"""
        self.root.configure(bg=self.bg_dark)
        
        # Configure ttk styles
        style = ttk.Style()
        style.theme_use('clam')
        
        # Configure colors
        style.configure(".", 
                       background=self.bg_dark,
                       foreground=self.fg_primary,
                       fieldbackground=self.bg_input,
                       bordercolor=self.bg_secondary,
                       selectbackground=self.accent_blue,
                       selectforeground=self.fg_primary)
        
        style.configure("TFrame", background=self.bg_dark)
        style.configure("TLabel", background=self.bg_dark, foreground=self.fg_primary)
        style.configure("TLabelframe", background=self.bg_dark, foreground=self.fg_primary)
        style.configure("TLabelframe.Label", background=self.bg_dark, foreground=self.fg_primary)
        
        style.configure("TButton",
                       background=self.accent_blue,
                       foreground=self.fg_primary,
                       borderwidth=0,
                       focuscolor='none',
                       padding=10)
        style.map("TButton",
                 background=[('active', '#106ebe'), ('disabled', self.bg_secondary)],
                 foreground=[('disabled', self.fg_secondary)])
        
        style.configure("TEntry",
                       fieldbackground=self.bg_input,
                       foreground=self.fg_primary,
                       bordercolor=self.bg_secondary,
                       insertcolor=self.fg_primary)
        
        style.configure("TProgressbar",
                       background=self.accent_blue,
                       troughcolor=self.bg_secondary,
                       bordercolor=self.bg_secondary,
                       lightcolor=self.accent_blue,
                       darkcolor=self.accent_blue)
        
    def setup_ui(self):
        # Main container with scrollbar
        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(main_container, bg=self.bg_dark, highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=680)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Mouse wheel scrolling
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        
        # Content padding
        content = ttk.Frame(scrollable_frame, padding="20")
        content.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = tk.Label(
            content, 
            text="🚀 TradingView to MT5 Setup Wizard",
            font=("Segoe UI", 18, "bold"),
            bg=self.bg_dark,
            fg=self.fg_primary
        )
        title_label.pack(pady=(0, 5))
        
        subtitle = tk.Label(
            content,
            text="Configure your automated trading bridge",
            font=("Segoe UI", 10),
            bg=self.bg_dark,
            fg=self.fg_secondary
        )
        subtitle.pack(pady=(0, 20))
        
        # Status label
        self.status_label = tk.Label(
            content,
            text="● Ready to setup",
            font=("Segoe UI", 10),
            bg=self.bg_dark,
            fg=self.accent_yellow
        )
        self.status_label.pack(pady=(0, 20))
        
        # Step 1: Create Directories
        step1_frame = ttk.LabelFrame(content, text=" 📁 Step 1: Initialize Project ", padding="20")
        step1_frame.pack(fill=tk.X, pady=(0, 15))
        
        tk.Label(step1_frame, text="Create required folder structure", 
                font=("Segoe UI", 9),
                bg=self.bg_dark,
                fg=self.fg_secondary).pack(anchor=tk.W, pady=(0,10))
        
        self.create_dir_btn = ttk.Button(
            step1_frame,
            text="Create Directories",
            command=self.create_directories
        )
        self.create_dir_btn.pack(pady=(0,10))
        
        self.dir_status = tk.Label(step1_frame, text="", 
                                   bg=self.bg_dark, fg=self.fg_secondary,
                                   font=("Segoe UI", 9))
        self.dir_status.pack()
        
        # Step 2: Install Requirements
        step2_frame = ttk.LabelFrame(content, text=" 📦 Step 2: Install Dependencies ", padding="20")
        step2_frame.pack(fill=tk.X, pady=(0, 15))
        
        tk.Label(step2_frame, text="Install required Python packages", 
                font=("Segoe UI", 9),
                bg=self.bg_dark,
                fg=self.fg_secondary).pack(anchor=tk.W, pady=(0,10))
        
        self.install_btn = ttk.Button(
            step2_frame,
            text="Install Requirements",
            command=self.install_requirements,
            state=tk.DISABLED
        )
        self.install_btn.pack(pady=(0,10))
        
        self.progress = ttk.Progressbar(step2_frame, mode='indeterminate', length=300)
        self.progress.pack()
        
        # Step 3: Configuration
        step3_frame = ttk.LabelFrame(content, text=" ⚙️ Step 3: Server Configuration ", padding="20")
        step3_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Create a grid layout for better organization
        config_grid = ttk.Frame(step3_frame)
        config_grid.pack(fill=tk.X)
        
        # Username
        tk.Label(config_grid, text="Username:", 
                font=("Segoe UI", 9, "bold"),
                bg=self.bg_dark, fg=self.fg_primary).grid(row=0, column=0, sticky=tk.W, pady=8)
        user_entry = ttk.Entry(config_grid, textvariable=self.basic_user, width=40)
        user_entry.grid(row=0, column=1, pady=8, padx=(15, 0), sticky=tk.EW)
        
        # Password
        tk.Label(config_grid, text="Password:", 
                font=("Segoe UI", 9, "bold"),
                bg=self.bg_dark, fg=self.fg_primary).grid(row=1, column=0, sticky=tk.W, pady=8)
        pass_entry = ttk.Entry(config_grid, textvariable=self.basic_password, show="●", width=40)
        pass_entry.grid(row=1, column=1, pady=8, padx=(15, 0), sticky=tk.EW)
        
        # Server URL
        tk.Label(config_grid, text="Server URL:", 
                font=("Segoe UI", 9, "bold"),
                bg=self.bg_dark, fg=self.fg_primary).grid(row=2, column=0, sticky=tk.W, pady=8)
        url_entry = ttk.Entry(config_grid, textvariable=self.external_base_url, width=40)
        url_entry.grid(row=2, column=1, pady=8, padx=(15, 0), sticky=tk.EW)
        
        config_grid.columnconfigure(1, weight=1)
        
        # Step 4: MT5 Configuration
        step4_frame = ttk.LabelFrame(content, text=" 📊 Step 4: MT5 Settings ", padding="20")
        step4_frame.pack(fill=tk.X, pady=(0, 15))
        
        # MT5 Executable
        tk.Label(step4_frame, text="MT5 Executable Path", 
                font=("Segoe UI", 9, "bold"),
                bg=self.bg_dark, fg=self.fg_primary).pack(anchor=tk.W, pady=(0,5))
        
        tk.Label(step4_frame, text="Select terminal64.exe from your MT5 installation", 
                font=("Segoe UI", 8),
                bg=self.bg_dark, fg=self.fg_secondary).pack(anchor=tk.W, pady=(0,8))
        
        path_frame = ttk.Frame(step4_frame)
        path_frame.pack(fill=tk.X, pady=(0,15))
        
        path1_entry = ttk.Entry(path_frame, textvariable=self.mt5_main_path)
        path1_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        browse1_btn = ttk.Button(path_frame, text="Browse", command=self.browse_main_path, width=12)
        browse1_btn.pack(side=tk.RIGHT)
        
        # Instances Directory (read-only info)
        tk.Label(step4_frame, text="Instances Directory", 
                font=("Segoe UI", 9, "bold"),
                bg=self.bg_dark, fg=self.fg_primary).pack(anchor=tk.W, pady=(10,5))
        
        tk.Label(step4_frame, text="Auto-created location for MT5 account instances", 
                font=("Segoe UI", 8),
                bg=self.bg_dark, fg=self.fg_secondary).pack(anchor=tk.W, pady=(0,8))
        
        instances_display = tk.Label(
            step4_frame,
            textvariable=self.mt5_instances_dir,
            font=("Segoe UI", 9),
            bg=self.bg_input,
            fg=self.fg_secondary,
            anchor=tk.W,
            padx=10,
            pady=8,
            relief=tk.FLAT
        )
        instances_display.pack(fill=tk.X)
        
        # Step 5: Launch
        step5_frame = ttk.LabelFrame(content, text=" 🚀 Step 5: Start Server ", padding="20")
        step5_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(step5_frame, text="Ready to launch your trading server", 
                font=("Segoe UI", 9),
                bg=self.bg_dark,
                fg=self.fg_secondary).pack(anchor=tk.W, pady=(0,15))
        
        self.start_btn = ttk.Button(
            step5_frame,
            text="🚀 Start Server",
            command=self.start_server,
            state=tk.DISABLED
        )
        self.start_btn.pack()
        
        # Pack canvas and scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
    def create_directories(self):
        """Create required directory structure"""
        try:
            directories = [
                'app',
                'app/copy_trading',
                'static', 
                'logs',
                'data',
                'data/commands',
                'mt5_instances',
                'backup'
            ]
            
            created = []
            for directory in directories:
                dir_path = self.base_dir / directory
                if not dir_path.exists():
                    dir_path.mkdir(parents=True, exist_ok=True)
                    created.append(directory)
                    
                    # Create .gitkeep in empty folders
                    if directory in ['data/commands', 'logs', 'backup']:
                        gitkeep_file = dir_path / '.gitkeep'
                        gitkeep_file.touch()
            
            if created:
                self.dir_status.config(
                    text=f"✓ Created: {', '.join(created)}",
                    fg=self.accent_green
                )
            else:
                self.dir_status.config(
                    text="✓ All directories exist",
                    fg=self.accent_green
                )
            
            # Enable next step
            self.install_btn.config(state=tk.NORMAL)
            self.create_dir_btn.config(state=tk.DISABLED)
            self.status_label.config(
                text="● Step 1 Complete → Install Requirements",
                fg=self.accent_green
            )
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create directories:\n{str(e)}")
            self.dir_status.config(text=f"✗ Error: {str(e)}", fg=self.accent_red)
    
    def browse_main_path(self):
        filename = filedialog.askopenfilename(
            title="Select MT5 Terminal Executable (terminal64.exe)",
            filetypes=[("Executable files", "*.exe"), ("All files", "*.*")]
        )
        if filename:
            self.mt5_main_path.set(filename)
    
    def install_requirements(self):
        self.install_btn.config(state=tk.DISABLED)
        self.progress.start()
        self.status_label.config(text="● Installing packages...", fg=self.accent_yellow)
        
        def install():
            try:
                requirements = """Flask==2.3.3
Flask-Limiter==2.8.1
Flask-Cors==4.0.0
python-dotenv==1.0.0
psutil==5.9.6
requests==2.31.0
werkzeug==2.3.7
"""
                with open("requirements.txt", "w") as f:
                    f.write(requirements)
                
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                    capture_output=True,
                    text=True
                )
                
                self.root.after(0, self.installation_complete, result.returncode == 0)
                
            except Exception as e:
                self.root.after(0, self.installation_complete, False, str(e))
        
        thread = threading.Thread(target=install)
        thread.daemon = True
        thread.start()
    
    def installation_complete(self, success, error=None):
        self.progress.stop()
        self.install_btn.config(state=tk.NORMAL)
        
        if success:
            self.status_label.config(
                text="● Step 2 Complete → Configure Settings",
                fg=self.accent_green
            )
            self.start_btn.config(state=tk.NORMAL)
            messagebox.showinfo(
                "Success", 
                "Dependencies installed successfully!\n\nPlease complete the configuration."
            )
        else:
            self.status_label.config(
                text="● Installation failed",
                fg=self.accent_red
            )
            messagebox.showerror("Error", f"Installation failed:\n{error if error else 'Unknown error'}")
    
    def validate_inputs(self):
        if not self.basic_user.get():
            messagebox.showwarning("Validation Error", "Please enter a username")
            return False
        if not self.basic_password.get():
            messagebox.showwarning("Validation Error", "Please enter a password")
            return False
        if len(self.basic_password.get()) < 6:
            messagebox.showwarning("Validation Error", "Password must be at least 6 characters")
            return False
        if not self.external_base_url.get():
            messagebox.showwarning("Validation Error", "Please enter server URL")
            return False
        if not self.mt5_main_path.get():
            messagebox.showwarning("Validation Error", "Please select MT5 executable")
            return False
        if not os.path.exists(self.mt5_main_path.get()):
            messagebox.showerror("Error", "MT5 executable not found")
            return False
        return True
    
    def start_server(self):
        if not self.validate_inputs():
            return
        
        try:
            import secrets
            secret_key = secrets.token_urlsafe(32)
            webhook_token = secrets.token_urlsafe(16)
            
            env_content = f"""# Server Configuration
SECRET_KEY={secret_key}
BASIC_USER={self.basic_user.get()}
BASIC_PASS={self.basic_password.get()}
EXTERNAL_BASE_URL={self.external_base_url.get()}

# Webhook Configuration
WEBHOOK_TOKEN={webhook_token}
WEBHOOK_RATE_LIMIT=60/minute

# MT5 Configuration
MT5_MAIN_PATH={self.mt5_main_path.get()}
MT5_PROFILE_SOURCE=
MT5_INSTANCES_DIR={self.mt5_instances_dir.get()}

# Email Configuration (Optional)
EMAIL_NOTIFICATIONS_ENABLED=false
SMTP_SERVER=
SMTP_PORT=587
SMTP_USE_TLS=true
SMTP_USER=
SMTP_PASS=
EMAIL_FROM=
EMAIL_TO=

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/trading_bot.log
"""
            
            with open(".env", "w") as f:
                f.write(env_content)
            
            if not os.path.exists("server.py"):
                self.create_server_file()
            
            webhook_url = f"{self.external_base_url.get()}/webhook/{webhook_token}"
            
            result = messagebox.askokcancel(
                "Ready to Launch",
                f"✓ Configuration complete!\n\n"
                f"Web Interface: {self.external_base_url.get()}\n"
                f"Username: {self.basic_user.get()}\n\n"
                f"Webhook URL:\n{webhook_url}\n\n"
                f"Start the server now?"
            )
            
            if result:
                self.status_label.config(text="● Server starting...", fg=self.accent_blue)
                
                if sys.platform == "win32":
                    subprocess.Popen('start cmd /k python server.py', shell=True)
                else:
                    subprocess.Popen([sys.executable, "server.py"])
                
                self.status_label.config(text="● Server is running!", fg=self.accent_green)
                
                messagebox.showinfo(
                    "Server Started",
                    f"Server is now running!\n\n"
                    f"Access: {self.external_base_url.get()}\n\n"
                    f"Use this webhook in TradingView:\n{webhook_url}"
                )
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start server:\n{str(e)}")
            self.status_label.config(text="● Error occurred", fg=self.accent_red)
    
    def create_server_file(self):
        """Create a basic server.py file"""
        server_content = """from flask import Flask, request, jsonify, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not (auth.username == os.getenv('BASIC_USER') and 
                           auth.password == os.getenv('BASIC_PASS')):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

@app.route('/')
@require_auth
def home():
    return send_from_directory('static', 'index.html')

@app.route('/health')
def health():
    return jsonify({'status': 'running', 'message': 'MT5 Bridge Server'})

@app.route('/webhook/<token>', methods=['POST'])
@limiter.limit(os.getenv('WEBHOOK_RATE_LIMIT', '60/minute'))
def webhook(token):
    if token != os.getenv('WEBHOOK_TOKEN'):
        return jsonify({'error': 'Invalid token'}), 403
    
    try:
        data = request.json
        print(f"Received webhook: {data}")
        return jsonify({'status': 'success', 'data': data})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
"""
        with open("server.py", "w") as f:
            f.write(server_content)

def main():
    root = tk.Tk()
    app = SetupWizard(root)
    root.mainloop()

if __name__ == "__main__":
    main()
