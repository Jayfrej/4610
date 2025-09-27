import os
import json
import logging
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
import base64
from dotenv import load_dotenv

# Import custom modules
from app.session_manager import SessionManager
from app.symbol_mapper import SymbolMapper
from app.email_handler import EmailHandler

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-here')

# Initialize rate limiter (alternative approach)
try:
    # Try new Flask-Limiter API
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["100 per hour"]
    )
    limiter.init_app(app)
except TypeError:
    # Fallback to old API
    limiter = Limiter(
        app,
        key_func=get_remote_address,
        default_limits=["100 per hour"]
    )

# Initialize components
session_manager = SessionManager()
symbol_mapper = SymbolMapper()
email_handler = EmailHandler()

# Setup logging
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('logs/trading_bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuration from .env
BASIC_USER = os.getenv('BASIC_USER', 'admin')
BASIC_PASS = os.getenv('BASIC_PASS', 'pass')
WEBHOOK_TOKEN = os.getenv('WEBHOOK_TOKEN', 'default-token')
EXTERNAL_BASE_URL = os.getenv('EXTERNAL_BASE_URL', 'http://localhost:5000')

def basic_auth_required(f):
    """Basic authentication decorator"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not (auth.username == BASIC_USER and auth.password == BASIC_PASS):
            logger.warning(f"[UNAUTHORIZED] Basic auth failed from {get_remote_address()}")
            email_handler.send_alert("Unauthorized Access", f"Failed basic auth from {get_remote_address()}")
            return ('Unauthorized', 401, {
                'WWW-Authenticate': 'Basic realm="Login Required"'
            })
        return f(*args, **kwargs)
    return decorated

def monitor_instances():
    """Background thread to monitor instance status"""
    while True:
        try:
            accounts = session_manager.get_all_accounts()
            for account_info in accounts:
                account = account_info['account']
                old_status = account_info.get('status', 'Unknown')
                
                if session_manager.is_instance_alive(account):
                    new_status = 'Online'
                else:
                    new_status = 'Offline'
                
                # Update status if changed
                if old_status != new_status:
                    session_manager.update_account_status(account, new_status)
                    logger.info(f"[STATUS_CHANGE] Account {account}: {old_status} -> {new_status}")
                    
                    # Send email notification
                    if new_status == 'Offline' and old_status == 'Online':
                        email_handler.send_alert("Instance Offline", f"Account {account} went offline")
                    elif new_status == 'Online' and old_status == 'Offline':
                        email_handler.send_alert("Instance Online", f"Account {account} came online")
            
            time.sleep(30)  # Check every 30 seconds
        except Exception as e:
            logger.error(f"[MONITOR_ERROR] {str(e)}")
            time.sleep(60)

# Start monitoring thread
monitor_thread = threading.Thread(target=monitor_instances, daemon=True)
monitor_thread.start()

@app.route('/')
@basic_auth_required
def index():
    """Main UI page"""
    return send_from_directory('static', 'index.html')

@app.route('/static/<path:filename>')
@basic_auth_required
def static_files(filename):
    """Serve static files"""
    return send_from_directory('static', filename)

@app.route('/health')
def health_check():
    """Health check endpoint for uptime monitoring"""
    try:
        accounts = session_manager.get_all_accounts()
        online_count = sum(1 for acc in accounts if acc.get('status') == 'Online')
        
        return jsonify({
            'ok': True,
            'timestamp': datetime.now().isoformat(),
            'total_accounts': len(accounts),
            'online_accounts': online_count,
            'instances': [{
                'account': acc['account'],
                'status': acc.get('status', 'Unknown'),
                'nickname': acc.get('nickname', ''),
                'pid': acc.get('pid'),
                'created': acc.get('created')
            } for acc in accounts]
        })
    except Exception as e:
        logger.error(f"[HEALTH_CHECK_ERROR] {str(e)}")
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/accounts', methods=['GET'])
@basic_auth_required
def get_accounts():
    """Get all accounts for UI table"""
    try:
        accounts = session_manager.get_all_accounts()
        return jsonify({'accounts': accounts})
    except Exception as e:
        logger.error(f"[GET_ACCOUNTS_ERROR] {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/accounts', methods=['POST'])
@basic_auth_required
def add_account():
    """Add new account"""
    try:
        data = request.get_json()
        account = data.get('account', '').strip()
        nickname = data.get('nickname', '').strip()
        
        if not account:
            return jsonify({'error': 'Account number is required'}), 400
        
        # Check if account already exists
        if session_manager.account_exists(account):
            return jsonify({'error': 'Account already exists'}), 400
        
        # Create instance
        success = session_manager.create_instance(account, nickname)
        if success:
            logger.info(f"[ACCOUNT_ADDED] Account {account} ({nickname}) created successfully")
            email_handler.send_alert("New Account Added", f"Account {account} ({nickname}) created and started")
            return jsonify({'success': True, 'message': 'Account created successfully'})
        else:
            return jsonify({'error': 'Failed to create account instance'}), 500
            
    except Exception as e:
        logger.error(f"[ADD_ACCOUNT_ERROR] {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/accounts/<account>/restart', methods=['POST'])
@basic_auth_required
def restart_account(account):
    """Restart account instance"""
    try:
        success = session_manager.restart_instance(account)
        if success:
            logger.info(f"[ACCOUNT_RESTARTED] Account {account}")
            return jsonify({'success': True, 'message': 'Account restarted successfully'})
        else:
            return jsonify({'error': 'Failed to restart account'}), 500
    except Exception as e:
        logger.error(f"[RESTART_ACCOUNT_ERROR] {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/accounts/<account>/stop', methods=['POST'])
@basic_auth_required
def stop_account(account):
    """Stop account instance"""
    try:
        success = session_manager.stop_instance(account)
        if success:
            logger.info(f"[ACCOUNT_STOPPED] Account {account}")
            return jsonify({'success': True, 'message': 'Account stopped successfully'})
        else:
            return jsonify({'error': 'Failed to stop account'}), 500
    except Exception as e:
        logger.error(f"[STOP_ACCOUNT_ERROR] {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/accounts/<account>/open', methods=['POST'])
@basic_auth_required
def open_account(account):
    """Open/Start account instance if offline"""
    try:
        if session_manager.is_instance_alive(account):
            # Already online, try to focus window
            session_manager.focus_instance(account)
            return jsonify({'success': True, 'message': 'Account is already online'})
        else:
            # Start the instance
            success = session_manager.start_instance(account)
            if success:
                logger.info(f"[ACCOUNT_OPENED] Account {account}")
                return jsonify({'success': True, 'message': 'Account opened successfully'})
            else:
                return jsonify({'error': 'Failed to open account'}), 500
    except Exception as e:
        logger.error(f"[OPEN_ACCOUNT_ERROR] {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/accounts/<account>', methods=['DELETE'])
@basic_auth_required
def delete_account(account):
    """Delete account"""
    try:
        success = session_manager.delete_instance(account)
        if success:
            logger.info(f"[ACCOUNT_DELETED] Account {account}")
            return jsonify({'success': True, 'message': 'Account deleted successfully'})
        else:
            return jsonify({'error': 'Failed to delete account'}), 500
    except Exception as e:
        logger.error(f"[DELETE_ACCOUNT_ERROR] {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/webhook-url')
@basic_auth_required
def get_webhook_url():
    """Get webhook URL for copy button"""
    webhook_url = f"{EXTERNAL_BASE_URL}/webhook/{WEBHOOK_TOKEN}"
    return jsonify({'url': webhook_url})

@app.route('/webhook/<token>', methods=['POST'])
@limiter.limit("10 per minute")
def webhook_handler(token):
    """Main webhook endpoint for trading signals"""
    try:
        # Validate token
        if token != WEBHOOK_TOKEN:
            logger.warning(f"[UNAUTHORIZED] Invalid webhook token from {get_remote_address()}")
            email_handler.send_alert("Unauthorized Webhook Access", f"Invalid token from {get_remote_address()}")
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Parse JSON payload
        try:
            data = request.get_json()
            if not data:
                raise ValueError("No JSON data received")
        except Exception as e:
            logger.error(f"[BAD_PAYLOAD] Invalid JSON: {str(e)}")
            email_handler.send_alert("Bad Webhook Payload", f"Invalid JSON from {get_remote_address()}: {str(e)}")
            return jsonify({'error': 'Invalid JSON payload'}), 400
        
        # Log incoming webhook
        logger.info(f"[WEBHOOK] Received: {json.dumps(data, ensure_ascii=False)}")
        
        # Validate required fields
        validation_result = validate_webhook_payload(data)
        if not validation_result['valid']:
            logger.error(f"[BAD_PAYLOAD] Validation failed: {validation_result['error']}")
            email_handler.send_alert("Bad Webhook Payload", f"Validation failed: {validation_result['error']}")
            return jsonify({'error': validation_result['error']}), 400
        
        # Process webhook
        result = process_webhook(data)
        
        if result['success']:
            logger.info(f"[WEBHOOK_SUCCESS] Processed successfully")
            return jsonify({'success': True, 'message': result['message']})
        else:
            logger.error(f"[WEBHOOK_ERROR] Processing failed: {result['error']}")
            email_handler.send_alert("Webhook Processing Error", f"Failed to process: {result['error']}")
            return jsonify({'error': result['error']}), 500
            
    except Exception as e:
        logger.error(f"[WEBHOOK_EXCEPTION] Unexpected error: {str(e)}")
        email_handler.send_alert("Webhook Exception", f"Unexpected error: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500

def validate_webhook_payload(data):
    """Validate webhook payload"""
    required_fields = ['symbol', 'action', 'volume']
    
    # Check for account(s)
    if 'account_number' not in data and 'accounts' not in data:
        return {'valid': False, 'error': 'Missing field: account_number or accounts'}
    
    # Check required fields
    for field in required_fields:
        if field not in data:
            return {'valid': False, 'error': f'Missing field: {field}'}
    
    # Validate action
    valid_actions = ['BUY', 'SELL', 'LONG', 'SHORT']
    if data['action'].upper() not in valid_actions:
        return {'valid': False, 'error': f'Invalid action. Must be one of: {valid_actions}'}
    
    # Set default order_type if not provided (Option A)
    if 'order_type' not in data:
        data['order_type'] = 'market'
    
    # Validate order_type specific requirements
    order_type = data['order_type'].lower()
    if order_type in ['limit', 'stop']:
        if 'price' not in data:
            return {'valid': False, 'error': f'price required for {order_type} orders'}
    
    # Validate volume
    try:
        volume = float(data['volume'])
        if volume <= 0:
            return {'valid': False, 'error': 'Volume must be positive'}
    except (ValueError, TypeError):
        return {'valid': False, 'error': 'Volume must be a number'}
    
    return {'valid': True}

def process_webhook(data):
    """Process validated webhook data"""
    try:
        # Get target accounts
        if 'accounts' in data:
            target_accounts = data['accounts']
        else:
            target_accounts = [data['account_number']]
        
        # Symbol mapping
        original_symbol = data['symbol']
        mapped_symbol = symbol_mapper.map_symbol(original_symbol)
        
        if not mapped_symbol:
            return {'success': False, 'error': f'Cannot map symbol: {original_symbol}'}
        
        logger.info(f"[SYMBOL_MAPPING] {original_symbol} → {mapped_symbol}")
        
        # Process for each account
        results = []
        for account in target_accounts:
            # Check if account exists and is online
            if not session_manager.account_exists(account):
                logger.warning(f"[ACCOUNT_NOT_FOUND] Account {account} not found")
                results.append({'account': account, 'success': False, 'error': 'Account not found'})
                continue
            
            if not session_manager.is_instance_alive(account):
                logger.warning(f"[ACCOUNT_OFFLINE] Account {account} is offline")
                results.append({'account': account, 'success': False, 'error': 'Account is offline'})
                continue
            
            # Prepare trading command
            command = prepare_trading_command(data, mapped_symbol, account)
            
            # TODO: Send command to MT5
            # Option 1: Write to MQL5\Files\... for EA to read
            # Option 2: Use MetaTrader5 Python library to send directly
            
            # For now, just log the command
            logger.info(f"[TRADING_COMMAND] Account {account}: {json.dumps(command, ensure_ascii=False)}")
            
            # Write command to file for EA to process (EA-pull method)
            file_result = write_command_for_ea(account, command)
            results.append({'account': account, 'success': file_result, 'command': command})
        
        # Summarize results
        success_count = sum(1 for r in results if r['success'])
        total_count = len(results)
        
        if success_count == total_count:
            return {'success': True, 'message': f'Command sent to {success_count}/{total_count} accounts'}
        elif success_count > 0:
            return {'success': True, 'message': f'Partial success: {success_count}/{total_count} accounts'}
        else:
            return {'success': False, 'error': 'Failed to send to any account'}
            
    except Exception as e:
        return {'success': False, 'error': str(e)}

def prepare_trading_command(data, mapped_symbol, account):
    """Prepare trading command structure"""
    # Normalize action
    action = data['action'].upper()
    if action in ['SELL', 'SHORT']:
        action = 'SELL'
    elif action in ['BUY', 'LONG']:
        action = 'BUY'
    
    command = {
        'timestamp': datetime.now().isoformat(),
        'account': account,
        'symbol': mapped_symbol,
        'original_symbol': data['symbol'],
        'action': action,
        'order_type': data.get('order_type', 'market'),
        'volume': float(data['volume']),
    }
    
    # Optional fields
    if 'price' in data:
        command['price'] = float(data['price'])
    if 'take_profit' in data:
        command['take_profit'] = float(data['take_profit'])
    if 'stop_loss' in data:
        command['stop_loss'] = float(data['stop_loss'])
    if 'comment' in data:
        command['comment'] = str(data['comment'])
    if 'deviation' in data:
        command['deviation'] = int(data['deviation'])
    
    return command

def write_command_for_ea(account, command):
    """Write trading command to file for EA to read"""
    try:
        # Get instance path
        instance_path = session_manager.get_instance_path(account)
        if not instance_path or not os.path.exists(instance_path):
            logger.error(f"[FILE_WRITE_ERROR] Instance path not found for account {account}")
            return False
        
        # Create MQL5/Files directory if not exists
        files_dir = os.path.join(instance_path, 'MQL5', 'Files')
        if not os.path.exists(files_dir):
            os.makedirs(files_dir)
        
        # Write command to JSON file
        filename = f"webhook_command_{int(time.time())}.json"
        filepath = os.path.join(files_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(command, f, ensure_ascii=False, indent=2)
        
        logger.info(f"[FILE_WRITTEN] Command written to {filepath}")
        return True
        
    except Exception as e:
        logger.error(f"[FILE_WRITE_ERROR] Account {account}: {str(e)}")
        return False

if __name__ == '__main__':
    logger.info("[STARTING] Trading Bot Server")
    logger.info(f"[CONFIG] Webhook endpoint: /webhook/{WEBHOOK_TOKEN}")
    logger.info(f"[CONFIG] External URL: {EXTERNAL_BASE_URL}")
    
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=os.getenv('DEBUG', 'False').lower() == 'true'
    )
