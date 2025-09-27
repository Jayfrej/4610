# MT5 Trading Bot - Multi-Account Webhook Manager

เว็บไซต์ตัวกลางสำหรับจัดการหลายบัญชี MetaTrader 5 พร้อมรับสัญญาณจาก TradingView ผ่าน Webhook

## ✨ ฟีเจอร์หลัก

### 🌐 Multi-Account Management
- เพิ่มบัญชี MT5 ได้ไม่จำกัด
- แต่ละบัญชีมี MT5 instance แยกกัน (Portable)
- Copy โปรไฟล์ Default พร้อม EA อัตโนมัติ
- ให้ผู้ใช้ล็อกอินเองเพื่อความปลอดภัย

### 📡 Webhook System
- รับสัญญาณจาก TradingView, 3Commas หรือระบบอื่น ๆ
- Symbol mapping อัตโนมัติ (Fuzzy matching)
- รองรับ Market, Limit, Stop, Close orders
- Rate limiting และ Token security

### 💻 Modern Web Interface
- Dashboard แสดงสถิติบัญชี (Online/Offline)
- จัดการบัญชีผ่าน UI (Open/Stop/Restart/Delete)
- Real-time status monitoring
- Mobile responsive design

### 🔒 Security Features
- Basic Authentication สำหรับ Web UI
- Webhook Token protection
- Cloudflare Tunnel support
- Email notifications

## 🚀 Quick Start

### 1. Setup ด่วน
```bash
# โคลนโปรเจ็กต์
git clone <repository-url>
cd mt5-trading-bot

# รัน Setup Wizard (แนะนำ)
python setup.py

# หรือ Manual Setup
pip install -r requirements.txt
copy .env.template .env
# แก้ไข .env ตามต้องการ
```

### 2. เตรียม MT5 Profile
1. เปิด MT5 → ตั้งค่า Charts, EA, Theme ตามต้องการ
2. บันทึกโปรไฟล์: `File → Profiles → Save As... → Default`
3. หาที่อยู่ Data Folder: `File → Open Data Folder`
4. บันทึก path ใส่ในไฟล์ `.env`

### 3. เริ่มใช้งาน
```bash
# เริ่มเซิร์ฟเวอร์
python server.py
# หรือ
start.bat

# เข้าเว็บไซต์
http://localhost:5000
```

## 📋 การกำหนดค่า (.env)

```ini
# Basic Authentication
BASIC_USER=admin
BASIC_PASS=your_secure_password

# Webhook Security
WEBHOOK_TOKEN=your_secure_token_here
EXTERNAL_BASE_URL=https://yourdomain.com

# MT5 Configuration
MT5_MAIN_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
MT5_INSTANCES_DIR=C:\trading_bot\mt5_instances  
MT5_PROFILE_SOURCE=C:\Users\YourName\AppData\Roaming\MetaQuotes\Terminal\XXXXX

# Email Notifications (Optional)
EMAIL_ENABLED=true
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_app_password
TO_EMAILS=alert@gmail.com
```

## 📝 Webhook Usage

### Endpoint
```
POST https://yourdomain.com/webhook/YOUR_TOKEN
Content-Type: application/json
```

### Message Format

**Market Order:**
```json
{
  "account_number": "1123456",
  "symbol": "XAUUSD", 
  "action": "BUY",
  "volume": 0.01,
  "take_profit": 2450.0,
  "stop_loss": 2400.0,
  "comment": "TV-Signal"
}
```

**Limit Order:**
```json
{
  "account_number": "1123456",
  "symbol": "EURUSD",
  "action": "SELL",
  "order_type": "limit",
  "price": 1.0950,
  "volume": 0.1
}
```

**Multiple Accounts:**
```json
{
  "accounts": ["1123456", "7890123"],
  "symbol": "BTCUSD",
  "action": "BUY", 
  "volume": 0.01
}
```

**Close Positions:**
```json
{
  "account_number": "1123456",
  "symbol": "XAUUSD",
  "order_type": "close"
}
```

**Close All Positions:**
```json
{
  "account_number": "1123456",
  "order_type": "close_all"
}
```

### TradingView Alert Setup
1. สร้าง Alert ใน TradingView
2. เลือก "Webhook URL"
3. ใส่ URL: `https://yourdomain.com/webhook/YOUR_TOKEN`
4. ใส่ Message JSON ตามตัวอย่างด้านบน

## 🏗️ System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   TradingView   │───▶│  Flask Server    │───▶│  MT5 Instance   │
│     Alert       │    │  (Webhook)       │    │   (Account 1)   │
└─────────────────┘    │                  │    └─────────────────┘
                       │  ┌─────────────┐ │    ┌─────────────────┐
┌─────────────────┐    │  │ Symbol      │ │───▶│  MT5 Instance   │
│   Web Browser   │───▶│  │ Mapper      │ │    │   (Account 2)   │
│     (UI)        │    │  └─────────────┘ │    └─────────────────┘
└─────────────────┘    │                  │    ┌─────────────────┐
                       │  ┌─────────────┐ │───▶│  MT5 Instance   │
                       │  │ Session     │ │    │   (Account N)   │
                       │  │ Manager     │ │    └─────────────────┘
                       └──┴─────────────┴─┘
```

## 📁 Project Structure

```
mt5-trading-bot/
├── app/                          # Core modules
│   ├── __init__.py
│   ├── session_manager.py        # MT5 instance management
│   ├── symbol_mapper.py          # Symbol mapping system
│   ├── mt5_handler.py           # Trading operations
│   ├── email_handler.py         # Email notifications
│   ├── symbol_fetcher.py        # Symbol discovery
│   └── config_manager.py        # Configuration management
├── static/                      # Web UI files
│   ├── index.html              # Main interface
│   ├── style.css               # Modern styling
│   └── app.js                  # Frontend JavaScript
├── logs/                       # Application logs
├── data/                       # Symbol mappings & cache
├── mt5_instances/              # MT5 instance directories
├── backup/                     # Configuration backups
├── server.py                   # Main Flask server
├── setup.py                    # Setup wizard
├── start.bat                   # Windows startup script
├── requirements.txt            # Python dependencies
├── .env.template              # Environment template
└── README.md                  # This file
```

## 🔧 Advanced Configuration

### Symbol Mapping
ระบบจะแมปสัญลักษณ์อัตโนมัติ เช่น:
- `xauusdm` → `XAUUSD`
- `eurusd.m` → `EURUSD`
- `btc` → `BTCUSD`

**เพิ่ม Custom Mapping:**
```python
from app.symbol_mapper import SymbolMapper
mapper = SymbolMapper()
mapper.add_custom_mapping("gold", "XAUUSD")
```

### Trading Methods
1. **File-based (แนะนำ):** เขียนไฟล์ JSON ให้ EA อ่าน
2. **Direct:** ใช้ MetaTrader5 Python library ยิงตรง

ตั้งค่าใน `.env`:
```ini
TRADING_METHOD=file    # หรือ direct
```

### Email Notifications
รองรับเหตุการณ์:
- ✅ Account Online/Offline
- ⚠️ Unauthorized access
- ❌ Bad webhook payload
- 📧 Trading signals processed

## 🌐 External Access (Cloudflare Tunnel)

### 1. ติดตั้ง Cloudflared
```bash
# Windows
winget install --id Cloudflare.cloudflared

# หรือดาวน์โหลดจาก GitHub
```

### 2. เชื่อมต่อ Tunnel
```bash
# Login to Cloudflare
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create mt5-bot

# Run tunnel
cloudflared tunnel --url http://localhost:5000
```

### 3. ตั้งค่า Security (แนะนำ)
**Firewall Rules:**
```javascript
// Allow only correct webhook endpoint
(http.request.uri.path eq "/webhook/YOUR_TOKEN" and http.request.method eq "POST")

// Block other webhook attempts  
(http.request.uri.path matches "^/webhook/.*" and http.request.uri.path ne "/webhook/YOUR_TOKEN")
```

**Rate Limiting:**
- 10 requests/minute สำหรับ `/webhook/*`
- Bot Fight Mode: ON

## 📊 Monitoring & Health Check

### Health Check Endpoint
```bash
GET /health
```

Response:
```json
{
  "ok": true,
  "total_accounts": 3,
  "online_accounts": 2,
  "instances": [...]
}
```

### Uptime Monitoring
ตั้ง UptimeRobot หรือ Uptime Kuma:
- URL: `https://yourdomain.com/health`
- Interval: 5 minutes
- Expected: `"ok": true`

### Log Monitoring
```bash
# Real-time logs
tail -f logs/trading_bot.log

# Error search
grep ERROR logs/trading_bot.log

# Webhook activity
grep WEBHOOK logs/trading_bot.log
```

## 🛠️ Troubleshooting

### MT5 เปิด 2 หน้าต่าง
**สาเหตุ:** Profile source ไม่ครบหรือ spawn ซ้ำ
```bash
# ตรวจสอบ MT5_PROFILE_SOURCE ต้องมี:
profiles/Default/
config/servers.dat
config/accounts.dat (optional)
```

### Webhook 400 Error
**ตรวจสอบ:**
- ✅ JSON format ถูกต้อง
- ✅ มี `account_number`, `symbol`, `action`, `volume`
- ✅ Token ใน URL ถูกต้อง
- ✅ Content-Type: application/json

### Status Offline ทั้งที่เปิดอยู่
**แก้ไข:** 
1. กด Restart ใน UI
2. ตรวจสอบ PID tracking
3. เช็คสิทธิ์ process

### Symbol Mapping ไม่ทำงาน
**แก้ไข:**
```python
# Test mapping
from app.symbol_mapper import SymbolMapper
mapper = SymbolMapper()
result = mapper.map_symbol("xauusdm")
print(result)  # Should return XAUUSD
```

## 🔄 Updates & Maintenance

### อัพเดทระบบ
```bash
# หยุดเซิร์ฟเวอร์
Ctrl+C

# Pull updates
git pull origin main

# Update dependencies  
pip install -r requirements.txt --upgrade

# เริ่มใหม่
python server.py
```

### Backup การตั้งค่า
```bash
# Backup important files
copy .env backup/
copy mt5_instances/accounts.db backup/
copy data/*.json backup/
```

### เปลี่ยน Webhook Token
```python
# ใน Python console
from app.config_manager import config
new_token = config.update_webhook_token()
print(f"New token: {new_token}")
```

## 📚 API Reference

### Protected Endpoints (Basic Auth)
- `GET /` - Web interface
- `GET /accounts` - Get all accounts
- `POST /accounts` - Add new account
- `POST /accounts/{id}/restart` - Restart account
- `POST /accounts/{id}/stop` - Stop account
- `DELETE /accounts/{id}` - Delete account
- `GET /webhook-url` - Get webhook URL

### Public Endpoints  
- `POST /webhook/{token}` - Receive trading signals
- `GET /health` - Health check

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

การเทรดในตลาด Forex และ CFD มีความเสี่ยงสูง ผู้ใช้ควรทำความเข้าใจและยอมรับความเสี่ยงก่อนใช้งาน ผู้พัฒนาไม่รับผิดชอบต่อความสูญเสียที่อาจเกิดขึ้น

---

## 🎯 Support

หากมีปัญหาหรือคำถาม:
1. เช็ค [Issues](../../issues) บน GitHub
2. อ่าน [INSTALL.md](INSTALL.md) สำหรับคำแนะนำการติดตั้งละเอียด
3. ดู logs ในโฟลเดอร์ `logs/`

**Happy Trading! 🚀📈**