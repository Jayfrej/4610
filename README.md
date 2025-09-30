# MT5 Multi-Account Webhook Trading Bot

A sophisticated web application designed to receive webhook signals from platforms like TradingView and execute trades across multiple MetaTrader 5 accounts simultaneously. This tool features a comprehensive user interface for managing accounts, monitoring instance status, and reviewing a detailed history log of all submitted orders. It also includes an integrated email notification system for alerts and a rate-limiting mechanism to prevent spam and ensure stable performance.

---

## Quick install

- [Installation](#installation)
- [Configuration](#configuration)
- [External Access](#external-access-cloudflare-tunnel)
- [Usage](#usage)
- [Webhook Integration](#webhook-integration)


---

## Quick Start

### Installation Steps
1. Install Python 3.8+ (check "Add Python to PATH")
2. Install dependencies: `pip install -r requirements.txt`
3. Run setup: `python setup.py`
4. Configure MT5 profile (save as "Default")
5. Start bot: `python server.py`

### Enable External Access
1. Install cloudflared
2. Create tunnel
3. Configure DNS
4. Run tunnel

---

## System Architecture

### System Flow Diagram

```
┌────────────────────┐        ┌─────────────────────┐        ┌────────────────────────┐
│ Signal Sources     │  POST  │  Flask Server & UI  │        │ Session Manager        │
│ (TradingView, etc) ├───────>│  /webhook/{TOKEN}   ├───────>│ + MT5 Handler          │
└────────────────────┘        └──────────┬──────────┘        └───────────┬────────────┘
                                          │                               │
                         File-bridge JSON │                               │ Launch/Track MT5
                                          v                               v
                              <InstanceRootPath>\              MT5 Instance(s)
                              <Account>\MQL5\Files\    ┌──>    EA (All-in-One)
                                                       │
                                                       └──>    Symbol Mapper (server-side)
```

### Working Modes

**FILE_BRIDGE (Recommended)**
- Server writes JSON to `...\<Account>\MQL5\Files\...`
- EA polls and processes commands
- More stable for multiple instances

**WEBHOOK_POST (Alternative)**
- EA calls `WebhookURL` at intervals
- Processes JSON response immediately
- Faster but requires EA configuration

### Data Flow Sequence

```
1. TradingView Alert
   ↓ POST webhook with JSON payload
   
2. Flask Server
   ↓ Token validation, JSON parsing, rate limiting
   
3. Symbol Mapper
   ↓ Normalize symbol (e.g., "XAUUSDM" → "XAUUSD")
   
4. Session Manager
   ↓ Verify account exists and is online
   
5. MT5 Handler
   ↓ Write JSON command to: <InstanceRootPath>\<Account>\MQL5\Files\webhook_command_[timestamp].json
   
6. MT5 Expert Advisor
   ↓ Read JSON, execute trade, delete file
   
7. Email Handler
   ↓ Send trade confirmation or error alert
   
8. Response
   → 200 OK or error message to TradingView
```

### Project Structure

**Server Side**
```
project-root/
├─ server.py                    # Main Flask app: routes, auth, rate-limit, health, monitor thread
├─ app/
│  ├─ __init__.py
│  ├─ session_manager.py        # Manage MT5 instances (start/stop/restart/focus, path, status)
│  ├─ symbol_mapper.py          # Map symbols from payload to actual MT5 symbol names
│  ├─ email_handler.py          # Email notifications (startup, online/offline, errors)
│  └─ trades.py                 # Record/read History Log + SSE /events/trades + /trades/clear
├─ static/                      # Serve UI files (client-side) via Flask
│  ├─ index.html                # Main UI page
│  ├─ style.css                 # Styles
│  └─ app.js                    # Client-side logic + SSE history
├─ mt5_instances/               # MT5 instance folders
├─ logs/
│  └─ trading_bot.log           # Server log file from server.py
├─ data/                        # Database and mappings
├─ backup/                      # Backup storage
├─ .env                         # Configuration (SECRET_KEY, BASIC_USER/PASS, WEBHOOK_TOKEN, SMTP, etc.)
├─ requirements.txt             # Python dependencies
└─ README.md
```

**MT5 Instance Side**
```
<InstanceRootPath>\
  └─ <AccountNumber>\
       └─ MQL5\
            └─ Files\
                ├─ webhook_command_17590xxxxx.json        ← Command files
                └─ instance_<AccountNumber>\              ← Junction by EA (if not Direct Mode)
```

**Important**: Write files to `...\<Account>\MQL5\Files\` only — DO NOT write to `...\Data\...` folder

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

---

## Key Features

### Core Functionality
- **Webhook Integration** - Receive trading commands via `POST /webhook/<token>`
  - Supports actions: `BUY/SELL/LONG/SHORT`, `CLOSE`, `CLOSE_ALL`, `CLOSE_SYMBOL`
- **Multi-Account Management** - Create/Open/Stop/Restart/Delete accounts through UI
- **Real-time History Log** - Command history with Server-Sent Events (SSE) + Clear button
- **Health Monitoring** - System health checks via `GET /health` and `GET /webhook/health`

### Security & Protection
- **Basic Authentication** - Password-protected UI interface
- **Rate Limiting** - Configurable webhook rate limits
- **Token-based Access** - Secure webhook endpoint authentication

### Monitoring & Alerts
- **Email Notifications** - Alert system for critical events:
  - System startup
  - Instance online/offline status
  - Payload validation errors
  - Trading execution alerts
  
  **Note**: System does NOT send emails for Basic Auth failures from `127.0.0.1` or internal health checks to reduce false alarms

### Trading Features
- **Portable MT5 Instances** - Each account runs in isolated instance
- **Symbol Auto-Mapping** - Intelligent symbol mapping with fuzzy matching
- **Market & Pending Orders** - Execute instant BUY/SELL, LIMIT, and STOP orders
- **Position Management** - Close specific positions, symbol positions, or all positions

---

## Requirements

### System Requirements
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

---

## Installation

### Step 1: Install Python
Download Python 3.8+ from [python.org](https://www.python.org/downloads/)
- Check "Add Python to PATH" during installation

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Run Setup Wizard
```bash
python setup.py
```

**The wizard will:**
- Check system requirements
- Create directory structure
- Configure profile source
- Generate security credentials
- Setup email notifications (optional)

### Step 4: Prepare MT5 Profile
1. Open your main MT5 installation
2. Configure settings (charts, templates, EAs, indicators)
3. Save as "Default" profile: **File → Profiles → Save As... → "Default"**

---

## Configuration

### Basic Configuration (.env)

```env
# ============================================
# AUTHENTICATION
# ============================================
BASIC_USER=admin
BASIC_PASS=your_secure_password

# ============================================
# SECURITY
# ============================================
SECRET_KEY=auto_generated_key
WEBHOOK_TOKEN=auto_generated_token
EXTERNAL_BASE_URL=http://localhost:5000

# ============================================
# SERVER
# ============================================
PORT=5000
DEBUG=False

# ============================================
# MT5 CONFIGURATION
# ============================================
MT5_MAIN_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
MT5_INSTANCES_DIR=mt5_instances
TRADING_METHOD=file

# ============================================
# EMAIL (OPTIONAL)
# ============================================
EMAIL_ENABLED=True
SENDER_EMAIL=your.email@gmail.com
SENDER_PASSWORD=your_app_password
RECIPIENTS=alert1@gmail.com,alert2@gmail.com

# ============================================
# SYMBOL MAPPING
# ============================================
SYMBOL_FETCH_ENABLED=False
FUZZY_MATCH_THRESHOLD=0.6

# ============================================
# RATE LIMITING
# ============================================
RATE_LIMIT_WEBHOOK=10 per minute
RATE_LIMIT_API=100 per hour
```

### Gmail Email Setup

1. Enable 2-Factor Authentication
2. Generate App Password:
   - Go to: Google Account → Security → 2-Step Verification → App passwords
3. Use generated password in `SENDER_PASSWORD`

---

## External Access (Cloudflare Tunnel)

### Quick Setup (4 Steps)

#### 1. Install Cloudflared

**Windows (PowerShell as Administrator):**
```powershell
winget install --id Cloudflare.cloudflared
```
Or download from: https://github.com/cloudflare/cloudflared/releases

#### 2. Login & Create Tunnel

```powershell
# Login
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create mt5-bot
```
Save the Tunnel ID from output

#### 3. Create Config File

Create file: `C:\Users\<Username>\.cloudflared\config.yml`

```yaml
tunnel: YOUR_TUNNEL_ID
credentials-file: C:\Users\<Username>\.cloudflared\YOUR_TUNNEL_ID.json

ingress:
  - hostname: webhook.yourdomain.com
    service: http://127.0.0.1:5000
    
  - hostname: yourdomain.com
    service: http://127.0.0.1:5000
    
  - service: http_status:404
```

**Replace:**
- `YOUR_TUNNEL_ID` = Tunnel ID from step 2
- `webhook.yourdomain.com` and `yourdomain.com` = your domain

#### 4. Setup DNS & Run

**Configure DNS (choose one):**

**Option A - Command Line:**
```powershell
cloudflared tunnel route dns mt5-bot webhook.yourdomain.com
cloudflared tunnel route dns mt5-bot yourdomain.com
```

**Option B - Cloudflare Dashboard:**
1. Go to DNS settings
2. Add CNAME record:
   - Name: `webhook` or `@`
   - Target: `YOUR_TUNNEL_ID.cfargotunnel.com`
   - Proxy: Enable (orange cloud)

**Run Tunnel:**
```powershell
cloudflared tunnel run mt5-bot
```

**Update .env:**
```env
EXTERNAL_BASE_URL=https://webhook.yourdomain.com
```

### Security Configuration (Recommended)

#### Cloudflare Firewall Rules

**Allow correct webhook endpoint:**
```
(http.request.uri.path eq "/webhook/YOUR_TOKEN" and http.request.method eq "POST")
```

**Block incorrect webhook attempts:**
```
(http.request.uri.path matches "^/webhook/.*" and http.request.uri.path ne "/webhook/YOUR_TOKEN")
```

#### Rate Limiting
- Set 10 requests/minute for `/webhook/*`
- Enable Bot Fight Mode: ON

---

## Usage

### Start the Bot

```bash
python server.py
```

**Access:**
- Local: `http://localhost:5000`
- External: `https://trading.yourdomain.com`

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

### View Command History

- Real-time command log displayed in UI
- Updates via Server-Sent Events (SSE)
- Clear history with "Clear" button

### Check System Health

**Endpoints:**
- `GET /health` - Overall system health
- `GET /webhook/health` - Webhook endpoint health

---

## Webhook Integration

### TradingView Setup

1. Create Alert in TradingView
2. Enable "Webhook URL"
3. Paste: `https://trading.yourdomain.com/webhook/YOUR_TOKEN`
4. Set alert message (JSON format)

### Webhook Payload Examples

#### Market Order (Single Account)
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

#### Multiple Accounts
```json
{
  "accounts": ["1123456", "7891011"],
  "symbol": "EURUSD",
  "action": "SELL",
  "volume": 0.1
}
```

#### Using TradingView Variables
```json
{
  "account_number": "1123456",
  "symbol": "{{ticker}}",
  "action": "{{strategy.order.comment}}",
  "volume": 0.05
}
```

#### Limit Order
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

#### Close Positions

**Close specific position:**
```json
{
  "account_number": "1123456",
  "action": "CLOSE",
  "ticket": 123456789
}
```

**Close all positions for symbol:**
```json
{
  "account_number": "1123456",
  "action": "CLOSE_SYMBOL",
  "symbol": "XAUUSD"
}
```

**Close all positions:**
```json
{
  "account_number": "1123456",
  "action": "CLOSE_ALL"
}
```

### Available Actions

| Action | Description |
|--------|-------------|
| `BUY` / `LONG` | Open buy position |
| `SELL` / `SHORT` | Open sell position |
| `CLOSE` | Close specific position |
| `CLOSE_SYMBOL` | Close all positions for symbol |
| `CLOSE_ALL` | Close all open positions |

### Symbol Mapping

**Automatic Mappings:**
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

---

## Troubleshooting

### MT5 Instance Won't Start

**Solutions:**
- Check `MT5_MAIN_PATH` in `.env`
- Manually run: `mt5_instances/[account]/launch_mt5_[account].bat`
- Check logs: `logs/trading_bot.log`

### Webhook Returns 401

**Solutions:**
- Verify webhook token matches `.env`
- Copy webhook URL from web interface

### Symbol Not Found

**Solutions:**
- Add custom mapping in `data/custom_mappings.json`
- Check symbol exists in MT5 Market Watch

### Email Not Working

**Solutions:**
- For Gmail: Use App Password, not regular password
- Verify SMTP settings in `.env`
- Check if email alerts are being filtered (localhost/health-check requests won't trigger emails)

### Cloudflare Tunnel Down

```bash
# Check service
sc query cloudflared

# Restart
net stop cloudflared
net start cloudflared
```

---

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

### Test Health Endpoints

```powershell
# System health
Invoke-WebRequest -Uri "http://localhost:5000/health"

# Webhook health
Invoke-WebRequest -Uri "http://localhost:5000/webhook/health"
```

---

## Best Practices

### Security

- Use strong passwords for Basic Auth
- Rotate webhook tokens every 3-6 months
- Enable email alerts for critical events
- Always use HTTPS (Cloudflare Tunnel)
- Keep software updated
- Review logs regularly

### Trading

- Start with 0.01 lot size
- Test on demo accounts first
- Always use stop loss
- Monitor execution daily
- Have manual backup plan
- Review command history regularly

### Maintenance

| Frequency | Tasks |
|-----------|-------|
| **Daily** | Check command history, verify instance status |
| **Weekly** | Review logs, check system health endpoints |
| **Monthly** | Clean logs, update packages, backup configs |
| **Quarterly** | Full system update, security audit, token rotation |

---

## Important Warnings

**Risk Warning**  
Trading involves significant loss risk. This bot executes YOUR strategy - it does NOT make trading decisions.

**System Requirements**  
Stable internet, powered-on Windows system, sufficient resources required 24/7.

**Security**  
Never share webhook token, use strong passwords, enable 2FA, review logs regularly.

**Testing**  
ALWAYS test on demo accounts first with minimum lot sizes.

**Email Alerts**  
Email system filters out Basic Auth failures from localhost/health-checks to prevent spam. Configure alerts appropriately.

---

## Backup

### Critical Files

```
.env
data/accounts.db
data/custom_mappings.json
config.yml (if using Cloudflare)
.cloudflared/ (if using Cloudflare)
logs/trading_bot.log
```

### Backup Command

```bash
xcopy .env backup\ /Y
xcopy data backup\data\ /Y /E
xcopy config.yml backup\ /Y
xcopy logs backup\logs\ /Y /E
```

### Automated Backup Script

Create `backup.bat`:
```batch
@echo off
set BACKUP_DIR=backup\%date:~-4%%date:~3,2%%date:~0,2%_%time:~0,2%%time:~3,2%
mkdir %BACKUP_DIR%
xcopy .env %BACKUP_DIR%\ /Y
xcopy data %BACKUP_DIR%\data\ /Y /E
xcopy config.yml %BACKUP_DIR%\ /Y
echo Backup completed: %BACKUP_DIR%
```

---

## Support

**For issues:**
1. Check logs: `logs/trading_bot.log`
2. Check system health: `GET /health`
3. Review command history in UI
4. Verify `.env` configuration
5. Test Cloudflare Tunnel connectivity
6. Check email notifications settings

---

**Version**: 1.0.0  
**Compatible**: MT5 Build 3801+, Python 3.8+, Windows 10/11

**Remember**: Discipline, risk management, and continuous learning are keys to successful trading. Use this tool wisely.
