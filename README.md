# MT5 Trading Bot - Multi-Account Webhook Manager

A Python-based trading bot for managing multiple MetaTrader 5 instances and executing trades via TradingView webhooks.

## Quick Navigation

- [📦 Installation](#installation) - Start here to install the bot
- [🌐 Cloudflare Tunnel Setup](#external-access-cloudflare-tunnel) - Setup HTTPS access
- [System Architecture](#system-architecture)
- [Configuration](#configuration)
- [Usage](#usage)
- [Webhook Integration](#webhook-integration)
- [Troubleshooting](#troubleshooting)

## System Architecture

### System Flow Diagram

```
+--------------------+        +---------------------+        +------------------------+
| Signal Sources     |  POST  |  Flask Server & UI  |        | Session Manager        |
| (TradingView, etc) +------->|  /webhook/{TOKEN}   +------->| + MT5 Handler          |
+--------------------+        +----------+----------+        +-----------+------------+
                                          |                               |
                         File-bridge JSON |                               | Launch/Track MT5
                                          v                               v
                              <InstanceRootPath>\              MT5 Instance(s)
                              <Account>\MQL5\Files\    +-->    EA (All-in-One)
                                                       |
                                                       +-->    Symbol Mapper (server-side)
```

### Working Modes

**FILE_BRIDGE (Recommended):**
- Server writes JSON file to `...\<Account>\MQL5\Files\...`
- EA polls and processes commands
- More stable for multiple instances

**WEBHOOK_POST (Alternative):**
- EA calls `WebhookURL` at intervals
- Processes JSON response immediately
- Faster but requires EA configuration

### Data Flow Sequence

```
1. TradingView Alert → POST webhook with JSON payload
   ↓
2. Flask Server → Token validation, JSON parsing, rate limiting
   ↓
3. Symbol Mapper → Normalize symbol (e.g., "XAUUSDM" → "XAUUSD")
   ↓
4. Session Manager → Verify account exists and is online
   ↓
5. MT5 Handler → Write JSON command to:
   <InstanceRootPath>\<Account>\MQL5\Files\webhook_command_[timestamp].json
   ↓
6. MT5 Expert Advisor → Read JSON, execute trade, delete file
   ↓
7. Email Handler → Send trade confirmation or error alert
   ↓
8. Response → 200 OK or error message to TradingView
```

### Project Structure (Server Side)

```
project-root/
├─ app/
│  ├─ session_manager.py        # Manage MT5 instance lifecycle
│  ├─ symbol_mapper.py          # Map symbols (suffix/alias support)
│  ├─ mt5_handler.py            # Python trading command layer (optional)
│  ├─ config_manager.py         # Config/environment variables
│  └─ email_handler.py          # Email notifications (optional)
├─ static/                      # UI (HTML/CSS/JS)
├─ mt5_instances/               # MT5 instance folders (important)
├─ logs/  data/  backup/        # Logs/data/backups
├─ server.py                    # Flask entrypoint
├─ setup.py                     # Setup wizard
├─ start.bat                    # Windows startup script
├─ requirements.txt
└─ .env.template
```

### Instance Root Path Structure (MT5 Side)

```
<InstanceRootPath>\
  └─ <AccountNumber>\
       └─ MQL5\
            └─ Files\
                ├─ webhook_command_17590xxxxx.json        ← Command files
                └─ (if not Direct Mode) instance_<AccountNumber>\  ← junction by EA
```

**Important:** Write files to `...\<Account>\MQL5\Files\` only — do NOT write to `...\Data\...` folder

### JSON Command Structure
```json
{
  "timestamp": "2025-09-29T10:30:00",
  "account": "1123456",
  "action": "BUY",
  "symbol": "XAUUSD",
  "original_symbol": "XAUUSDM",
  "volume": 0.01,
  "take_profit": 2450.0,
  "stop_loss": 2400.0
}
```

## Features

- **Multi-Account Management**: Manage unlimited MT5 accounts from a single interface
- **Portable MT5 Instances**: Each account runs in an isolated instance
- **TradingView Webhook Integration**: Execute trades directly from TradingView alerts
- **Real-time Monitoring**: Track account status, PIDs, and connection health
- **Email Notifications**: Error reporting and trade alerts
- **Symbol Auto-Mapping**: Intelligent symbol mapping with fuzzy matching
- **Market & Pending Orders**: Execute instant BUY/SELL, LIMIT, and STOP orders
- **Position Management**: Close specific positions, symbol positions, or all positions

## Requirements

### System
- **OS**: Windows 10/11 (64-bit)
- **Python**: 3.8+
- **RAM**: 4GB minimum (8GB+ for multiple instances)
- **Disk Space**: 500MB per MT5 instance
- **MetaTrader 5**: Installed and configured

### Python Dependencies
```
Flask==2.3.3
Flask-Limiter==2.8.1
python-dotenv==1.0.0
psutil==5.9.6
requests==2.31.0
werkzeug==2.3.7
```

## Installation

### 1. Install Python
Download Python 3.8+ from [python.org](https://www.python.org/downloads/)
- Check "Add Python to PATH" during installation

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Setup Wizard
```bash
python setup.py
```

The wizard will:
- Check system requirements
- Create directory structure
- Configure profile source
- Generate security credentials
- Setup email notifications (optional)

### 4. Prepare MT5 Profile
1. Open your main MT5 installation
2. Configure settings (charts, templates, EAs, indicators)
3. Save as "Default" profile: **File → Profiles → Save As... → "Default"**

## Configuration

### Basic Configuration (.env)
```env
# Authentication
BASIC_USER=admin
BASIC_PASS=your_secure_password

# Security
SECRET_KEY=auto_generated_key
WEBHOOK_TOKEN=auto_generated_token
EXTERNAL_BASE_URL=http://localhost:5000

# Server
PORT=5000
DEBUG=False

# MT5 Configuration
MT5_MAIN_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
MT5_INSTANCES_DIR=mt5_instances
TRADING_METHOD=file

# Email (Optional)
EMAIL_ENABLED=True
SENDER_EMAIL=your.email@gmail.com
SENDER_PASSWORD=your_app_password
RECIPIENTS=alert1@gmail.com,alert2@gmail.com

# Symbol Mapping
SYMBOL_FETCH_ENABLED=False
FUZZY_MATCH_THRESHOLD=0.6

# Rate Limiting
RATE_LIMIT_WEBHOOK=10 per minute
RATE_LIMIT_API=100 per hour
```

### Gmail Email Setup
1. Enable 2-Factor Authentication
2. Generate App Password: Google Account → Security → 2-Step Verification → App passwords
3. Use generated password in SENDER_PASSWORD

## External Access (Cloudflare Tunnel)

### 1. Install Cloudflared

**Windows:**
```bash
# Using winget
winget install --id Cloudflare.cloudflared

# Or download from GitHub
# https://github.com/cloudflare/cloudflared/releases
```

### 2. Setup Tunnel

**Quick Temporary Tunnel (Testing):**
```bash
# Start bot first
python server.py

# In new terminal, start tunnel
cloudflared tunnel --url http://localhost:5000

# Copy the HTTPS URL and update .env
EXTERNAL_BASE_URL=https://random-words-1234.trycloudflare.com
```

**Permanent Tunnel (Production):**
```bash
# Login to Cloudflare
cloudflared tunnel login

# Create named tunnel
cloudflared tunnel create mt5-bot

# Run tunnel
cloudflared tunnel --url http://localhost:5000
```

### 3. Security Configuration (Recommended)

**Cloudflare Firewall Rules:**

Allow correct webhook endpoint:
```
(http.request.uri.path eq "/webhook/YOUR_TOKEN" and http.request.method eq "POST")
```

Block incorrect webhook attempts:
```
(http.request.uri.path matches "^/webhook/.*" and http.request.uri.path ne "/webhook/YOUR_TOKEN")
```

**Rate Limiting:**
- Set 10 requests/minute for `/webhook/*`
- Enable Bot Fight Mode: ON

**Install as Windows Service:**
```bash
cloudflared service install
net start cloudflared
```

## Usage

### Start the Bot
```bash
python server.py
```
Access: `http://localhost:5000` or `https://trading.yourdomain.com`

### Add MT5 Account
1. Open web interface
2. Click "Add MT5 Account"
3. Enter account number and nickname
4. Click "Add Account"
5. MT5 terminal opens automatically - login with your credentials

### Manage Accounts
- **Restart**: Stop and restart instance
- **Stop**: Terminate MT5 process
- **Open**: Start offline instance
- **Delete**: Remove instance and files

## Webhook Integration

### TradingView Setup
1. Create Alert in TradingView
2. Enable "Webhook URL"
3. Paste: `https://trading.yourdomain.com/webhook/YOUR_TOKEN`
4. Set alert message (JSON format)

### Webhook Payload Examples

**Market Order (Single Account)**
```json
{
  "account_number": "1123456",
  "symbol": "XAUUSD",
  "action": "BUY",
  "volume": 0.01,
  "take_profit": 2450.0,
  "stop_loss": 2400.0
}
```

**Multiple Accounts**
```json
{
  "accounts": ["1123456", "7891011"],
  "symbol": "EURUSD",
  "action": "SELL",
  "volume": 0.1
}
```

**Using TradingView Variables**
```json
{
  "account_number": "1123456",
  "symbol": "{{ticker}}",
  "action": "{{strategy.order.comment}}",
  "volume": 0.05
}
```

**Limit Order**
```json
{
  "account_number": "1123456",
  "symbol": "EURUSD",
  "action": "BUY",
  "order_type": "limit",
  "price": 1.0850,
  "volume": 0.1
}
```

**Close Positions**
```json
// Close specific position
{"account_number": "1123456", "action": "CLOSE", "ticket": 123456789}

// Close all positions for symbol
{"account_number": "1123456", "action": "CLOSE_SYMBOL", "symbol": "XAUUSD"}

// Close all positions
{"account_number": "1123456", "action": "CLOSE_ALL"}
```

### Actions
- **BUY/LONG**: Open buy position
- **SELL/SHORT**: Open sell position
- **CLOSE**: Close specific position
- **CLOSE_SYMBOL**: Close all positions for symbol
- **CLOSE_ALL**: Close all open positions

### Symbol Mapping
The bot automatically maps symbols:
- `XAUUSDM` → `XAUUSD`
- `GOLD` → `XAUUSD`
- `EURUSD.` → `EURUSD`

**Custom Mappings** (`data/custom_mappings.json`):
```json
{
  "goldspot": "XAUUSD",
  "btc": "BTCUSD",
  "sp500": "US500"
}
```

## Troubleshooting

### MT5 Instance Won't Start
- Check `MT5_MAIN_PATH` in `.env`
- Manually run: `mt5_instances/[account]/launch_mt5_[account].bat`
- Check logs: `logs/trading_bot.log`

### Webhook Returns 401
- Verify webhook token matches `.env`
- Copy webhook URL from web interface

### Symbol Not Found
- Add custom mapping in `data/custom_mappings.json`
- Check symbol exists in MT5 Market Watch

### Email Not Working
- For Gmail: Use App Password, not regular password
- Verify SMTP settings in `.env`

### Cloudflare Tunnel Down
```bash
# Check service
sc query cloudflared

# Restart
net stop cloudflared
net start cloudflared
```

## Testing

### Test Webhook Locally
```powershell
$body = @{
    account_number = "1123456"
    symbol = "XAUUSD"
    action = "BUY"
    volume = 0.01
} | ConvertTo-Json

Invoke-WebRequest -Uri "http://localhost:5000/webhook/YOUR_TOKEN" `
    -Method POST -ContentType "application/json" -Body $body
```

### Test via Cloudflare
```powershell
Invoke-WebRequest -Uri "https://trading.yourdomain.com/webhook/YOUR_TOKEN" `
    -Method POST -ContentType "application/json" -Body $body
```

## Best Practices

### Security
- Use strong passwords
- Rotate webhook tokens every 3-6 months
- Enable email alerts
- Always use HTTPS (Cloudflare Tunnel)
- Keep software updated

### Trading
- Start with 0.01 lot size
- Test on demo accounts first
- Always use stop loss
- Monitor execution daily
- Have manual backup plan

### Maintenance
**Weekly**: Review logs, check instance status
**Monthly**: Clean logs, update packages, backup configs
**Quarterly**: Full system update, security audit

## Important Warnings

⚠️ **Risk Warning**: Trading involves significant loss risk. This bot executes YOUR strategy - it does NOT make trading decisions.

⚠️ **System Requirements**: Stable internet, powered-on Windows system, sufficient resources required 24/7.

⚠️ **Security**: Never share webhook token, use strong passwords, enable 2FA, review logs regularly.

⚠️ **Testing**: ALWAYS test on demo accounts first with minimum lot sizes.

## Backup

**Critical Files**:
```
.env
data/accounts.db
data/custom_mappings.json
config.yml (if using Cloudflare)
.cloudflared/ (if using Cloudflare)
```

**Backup Command**:
```bash
xcopy .env backup\ /Y
xcopy data backup\data\ /Y /E
xcopy config.yml backup\ /Y
```

## Support

For issues:
1. Check logs: `logs/trading_bot.log`
2. Review troubleshooting section
3. Verify `.env` configuration
4. Test Cloudflare Tunnel connectivity

---

**Version**: 1.0.0  
**Compatible**: MT5 Build 3801+, Python 3.8+, Windows 10/11

**Remember**: Discipline, risk management, and continuous learning are keys to successful trading. Use this tool wisely!
