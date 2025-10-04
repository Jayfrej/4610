import os
import json
import logging
import threading
import time
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, session
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
from app.trades import trades_bp, init_trades, record_and_broadcast  

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-here')

# Session cookie config
SESSION_COOKIE_SECURE = False
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=SESSION_COOKIE_SECURE,
)

# Initialize rate limiter
try:
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["100 per hour"]
    )
    limiter.init_app(app)
except TypeError:
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

# ✅ Register trades blueprint
app.register_blueprint(trades_bp)

def basic_auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not (auth.username == BASIC_USER and auth.password == BASIC_PASS):
            logger.warning(f"[UNAUTHORIZED] Basic auth failed from {get_remote_address()}")
            email_handler.send_alert("Unauthorized Access", f"Failed basic auth from {get_remote_address()}")
            return ('Unauthorized', 401, {
                'WWW-Authenticate': 'Basic realm=\"Login Required\"'
            })
        return f(*args, **kwargs)
    return decorated

def session_login_required(f):
    @wraps(f)
    def _wrap(*args, **kwargs):
        if not session.get('auth'):
            return jsonify({'error': 'Auth required'}), 401
        return f(*args, **kwargs)
    return _wrap

@app.post('/login')
def login_api():
    data = request.get_json(silent=True) or {}
    user = data.get('username', '')
    pwd = data.get('password', '')
    if user == BASIC_USER and pwd == BASIC_PASS:
        session['auth'] = True
        return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'Invalid credentials'}), 401

def monitor_instances():
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
                
                if old_status != new_status:
                    session_manager.update_account_status(account, new_status)
                    logger.info(f"[STATUS_CHANGE] Account {account}: {old_status} -> {new_status}")
                    
                    if new_status == 'Offline' and old_status == 'Online':
                        email_handler.send_alert("Instance Offline", f"Account {account} went offline")
                    elif new_status == 'Online' and old_status == 'Offline':
                        email_handler.send_alert("Instance Online", f"Account {account} came online")
            
            time.sleep(30)
        except Exception as e:
            logger.error(f"[MONITOR_ERROR] {str(e)}")
            time.sleep(60)

# Start monitoring thread
monitor_thread = threading.Thread(target=monitor_instances, daemon=True)
monitor_thread.start()

# Error handlers
@app.errorhandler(405)
def method_not_allowed(error):
    logger.warning(f"[METHOD_NOT_ALLOWED] {request.method} {request.path} from {get_remote_address()}")
    return jsonify({'error': 'Method not allowed'}), 405

@app.errorhandler(404)
def not_found(error):
    logger.warning(f"[NOT_FOUND] {request.method} {request.path} from {get_remote_address()}")
    return jsonify({'error': 'Endpoint not found'}), 404

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

@app.route('/health', methods=['GET', 'HEAD'])
def health_check():
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

@app.route('/webhook/health', methods=['GET', 'HEAD'])
def webhook_health():
    return jsonify({
        'status': 'ok',
        'webhook_status': 'active',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/webhook/', methods=['GET'])
@app.route('/webhook', methods=['GET'])
def webhook_info():
    return jsonify({
        'message': 'Webhook endpoint active',
        'supported_methods': ['POST'],
        'health_check': '/webhook/health',
        'endpoint_format': '/webhook/{token}',
        'supported_actions': ['BUY', 'SELL', 'LONG', 'SHORT', 'CLOSE', 'CLOSE_ALL', 'CLOSE_SYMBOL'],
        'timestamp': datetime.now().isoformat()
    })

@app.route('/accounts', methods=['GET'])
@session_login_required
def get_accounts():
    try:
        accounts = session_manager.get_all_accounts()
        return jsonify({'accounts': accounts})
    except Exception as e:
        logger.error(f"[GET_ACCOUNTS_ERROR] {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/accounts', methods=['POST'])
@session_login_required
def add_account():
    try:
        data = request.get_json()
        account = data.get('account', '').strip()
        nickname = data.get('nickname', '').strip()
        
        if not account:
            return jsonify({'error': 'Account number is required'}), 400
        
        if session_manager.account_exists(account):
            return jsonify({'error': 'Account already exists'}), 400
        
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
@session_login_required
def restart_account(account):
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
@session_login_required
def stop_account(account):
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
@session_login_required
def open_account(account):
    try:
        if session_manager.is_instance_alive(account):
            session_manager.focus_instance(account)
            return jsonify({'success': True, 'message': 'Account is already online'})
        else:
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
@session_login_required
def delete_account(account):
    try:
        success = session_manager.delete_instance(account)
        if success:
            logger.info(f"[ACCOUNT_DELETED] Account {account}")
            
            # ✅ ลบ trade history ของ account นี้ด้วย
            try:
                from trades import delete_account_history
                deleted_count = delete_account_history(account)
                logger.info(f"[HISTORY_DELETED] Removed {deleted_count} trades for account {account}")
            except Exception as e:
                logger.warning(f"[HISTORY_DELETE_ERROR] {str(e)}")
            
            return jsonify({'success': True, 'message': 'Account deleted successfully'})
        else:
            return jsonify({'error': 'Failed to delete account'}), 500
    except Exception as e:
        logger.error(f"[DELETE_ACCOUNT_ERROR] {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/webhook-url')
@session_login_required
def get_webhook_url():
    webhook_url = f"{EXTERNAL_BASE_URL}/webhook/{WEBHOOK_TOKEN}"
    return jsonify({'url': webhook_url})

@app.route('/webhook/<token>', methods=['POST'])
@limiter.limit("10 per minute")
def webhook_handler(token):
    try:
        if token != WEBHOOK_TOKEN:
            logger.warning(f"[UNAUTHORIZED] Invalid webhook token from {get_remote_address()}")
            email_handler.send_alert("Unauthorized Webhook Access", f"Invalid token from {get_remote_address()}")
            return jsonify({'error': 'Unauthorized'}), 401
        
        try:
            data = request.get_json()
            if not data:
                raise ValueError("No JSON data received")
        except Exception as e:
            logger.error(f"[BAD_PAYLOAD] Invalid JSON: {str(e)}")
            email_handler.send_alert("Bad Webhook Payload", f"Invalid JSON from {get_remote_address()}: {str(e)}")
            return jsonify({'error': 'Invalid JSON payload'}), 400
        
        logger.info(f"[WEBHOOK] Received: {json.dumps(data, ensure_ascii=False)}")
        
        validation_result = validate_webhook_payload(data)
        if not validation_result['valid']:
            logger.error(f"[BAD_PAYLOAD] Validation failed: {validation_result['error']}")
            email_handler.send_alert("Bad Webhook Payload", f"Validation failed: {validation_result['error']}")
            return jsonify({'error': validation_result['error']}), 400
        
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
    required_fields = ['action']
    
    if 'account_number' not in data and 'accounts' not in data:
        return {'valid': False, 'error': 'Missing field: account_number or accounts'}
    
    for field in required_fields:
        if field not in data:
            return {'valid': False, 'error': f'Missing field: {field}'}
    
    action = data['action'].upper()
    
    if action in ['BUY', 'SELL', 'LONG', 'SHORT']:
        if 'symbol' not in data:
            return {'valid': False, 'error': 'symbol required for trading actions'}
        if 'volume' not in data:
            return {'valid': False, 'error': 'volume required for trading actions'}
        
        if 'order_type' not in data:
            data['order_type'] = 'market'
        
        order_type = data['order_type'].lower()
        if order_type in ['limit', 'stop']:
            if 'price' not in data:
                return {'valid': False, 'error': f'price required for {order_type} orders'}
        
        try:
            volume = float(data['volume'])
            if volume <= 0:
                return {'valid': False, 'error': 'Volume must be positive'}
        except (ValueError, TypeError):
            return {'valid': False, 'error': 'Volume must be a number'}
            
    elif action in ['CLOSE', 'CLOSE_ALL', 'CLOSE_SYMBOL']:
        if action == 'CLOSE':
            if 'ticket' not in data and 'symbol' not in data:
                return {'valid': False, 'error': 'ticket or symbol required for CLOSE action'}
            
            if 'ticket' in data:
                try:
                    int(data['ticket'])
                except (ValueError, TypeError):
                    return {'valid': False, 'error': 'ticket must be a number'}
                    
        elif action == 'CLOSE_SYMBOL':
            if 'symbol' not in data:
                return {'valid': False, 'error': 'symbol required for CLOSE_SYMBOL action'}
        
        if 'volume' in data:
            try:
                volume = float(data['volume'])
                if volume <= 0:
                    return {'valid': False, 'error': 'Volume must be positive'}
            except (ValueError, TypeError):
                return {'valid': False, 'error': 'Volume must be a number'}
        
        if 'position_type' in data:
            position_type = data['position_type'].upper()
            if position_type not in ['BUY', 'SELL']:
                return {'valid': False, 'error': 'position_type must be BUY or SELL'}
                
    else:
        valid_actions = ['BUY', 'SELL', 'LONG', 'SHORT', 'CLOSE', 'CLOSE_ALL', 'CLOSE_SYMBOL']
        return {'valid': False, 'error': f'Invalid action. Must be one of: {valid_actions}'}
    
    return {'valid': True}

def process_webhook(data):
    try:
        if 'accounts' in data:
            target_accounts = data['accounts']
        else:
            target_accounts = [data['account_number']]
        
        action = data['action'].upper()
        mapped_symbol = None
        
        if action in ['BUY', 'SELL', 'LONG', 'SHORT', 'CLOSE_SYMBOL'] or (action == 'CLOSE' and 'symbol' in data):
            original_symbol = data['symbol']
            mapped_symbol = symbol_mapper.map_symbol(original_symbol)
            
            if not mapped_symbol:
                return {'success': False, 'error': f'Cannot map symbol: {original_symbol}'}
            
            logger.info(f"[SYMBOL_MAPPING] {original_symbol} → {mapped_symbol}")
        
        results = []
        for account in target_accounts:
            if not session_manager.account_exists(account):
                logger.warning(f"[ACCOUNT_NOT_FOUND] Account {account} not found")
                
                # ✅ บันทึก error ลง history
                record_and_broadcast({
                    'status': 'error',
                    'action': action,
                    'symbol': data.get('symbol', '-'),
                    'account': account,
                    'volume': data.get('volume', ''),
                    'price': data.get('price', ''),
                    'message': 'Account not found',
                })
                
                results.append({'account': account, 'success': False, 'error': 'Account not found'})
                continue
            
            if not session_manager.is_instance_alive(account):
                logger.warning(f"[ACCOUNT_OFFLINE] Account {account} is offline")
                
                # ✅ บันทึก error ลง history
                record_and_broadcast({
                    'status': 'error',
                    'action': action,
                    'symbol': data.get('symbol', '-'),
                    'account': account,
                    'volume': data.get('volume', ''),
                    'price': data.get('price', ''),
                    'message': 'Account is offline',
                })
                
                results.append({'account': account, 'success': False, 'error': 'Account is offline'})
                continue
            
            command = prepare_trading_command(data, mapped_symbol, account)
            
            logger.info(f"[{action}_COMMAND] Account {account}: {json.dumps(command, ensure_ascii=False)}")
            
            file_result = write_command_for_ea(account, command)
            
            # ✅ บันทึก success ลง history
            if file_result:
                record_and_broadcast({
                    'status': 'success',
                    'action': action,
                    'symbol': mapped_symbol or data.get('symbol', '-'),
                    'account': account,
                    'volume': data.get('volume', ''),
                    'price': data.get('price', ''),
                    'message': f'{action} command sent to EA',
                })
            
            results.append({
                'account': account, 
                'success': file_result, 
                'command': command,
                'action': action
            })
        
        success_count = sum(1 for r in results if r['success'])
        total_count = len(results)
        
        if action in ['CLOSE', 'CLOSE_ALL', 'CLOSE_SYMBOL']:
            action_desc = {
                'CLOSE': 'Close position',
                'CLOSE_ALL': 'Close all positions', 
                'CLOSE_SYMBOL': f'Close {data.get("symbol", "")} positions'
            }.get(action, action)
        else:
            action_desc = f'{action} command'
        
        if success_count == total_count:
            return {'success': True, 'message': f'{action_desc} sent to {success_count}/{total_count} accounts'}
        elif success_count > 0:
            return {'success': True, 'message': f'{action_desc} partial success: {success_count}/{total_count} accounts'}
        else:
            return {'success': False, 'error': f'Failed to send {action_desc} to any account'}
            
    except Exception as e:
        return {'success': False, 'error': str(e)}

def prepare_trading_command(data, mapped_symbol, account):
    action = data['action'].upper()
    
    command = {
        'timestamp': datetime.now().isoformat(),
        'account': account,
        'action': action,
    }
    
    if action in ['BUY', 'SELL', 'LONG', 'SHORT']:
        if action in ['SELL', 'SHORT']:
            action = 'SELL'
        elif action in ['BUY', 'LONG']:
            action = 'BUY'
        
        command.update({
            'action': action,
            'symbol': mapped_symbol,
            'original_symbol': data['symbol'],
            'order_type': data.get('order_type', 'market'),
            'volume': float(data['volume']),
        })
        
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
    
    elif action == 'CLOSE':
        command['action'] = 'CLOSE'
        
        if 'ticket' in data:
            command['ticket'] = int(data['ticket'])
        
        if 'symbol' in data:
            command['symbol'] = mapped_symbol if mapped_symbol else data['symbol']
            command['original_symbol'] = data['symbol']
        
        if 'volume' in data:
            try:
                command['volume'] = float(data['volume'])
            except (ValueError, TypeError):
                pass
        
        if 'comment' in data:
            command['comment'] = str(data['comment'])
    
    elif action == 'CLOSE_ALL':
        command['action'] = 'CLOSE_ALL'
        
        if 'position_type' in data:
            position_type = data['position_type'].upper()
            if position_type in ['BUY', 'SELL']:
                command['position_type'] = position_type
        
        if 'comment' in data:
            command['comment'] = str(data['comment'])
    
    elif action == 'CLOSE_SYMBOL':
        command.update({
            'action': 'CLOSE_SYMBOL',
            'symbol': mapped_symbol,
            'original_symbol': data['symbol'],
        })
        
        if 'position_type' in data:
            position_type = data['position_type'].upper()
            if position_type in ['BUY', 'SELL']:
                command['position_type'] = position_type
        
        if 'comment' in data:
            command['comment'] = str(data['comment'])
    
    return command

def write_command_for_ea(account, command):
    try:
        instance_path = session_manager.get_instance_path(account)
        if not instance_path or not os.path.exists(instance_path):
            logger.error(f"[FILE_WRITE_ERROR] Instance path not found for account {account}")
            return False
        
        files_dirs = [
            os.path.join(instance_path, 'MQL5', 'Files'),
            os.path.join(instance_path, 'Data', 'MQL5', 'Files')
        ]
        
        files_dir = None
        for dir_path in files_dirs:
            if not os.path.exists(dir_path):
                try:
                    os.makedirs(dir_path, exist_ok=True)
                    files_dir = dir_path
                    break
                except Exception:
                    continue
            else:
                files_dir = dir_path
                break
        
        if not files_dir:
            logger.error(f"[FILE_WRITE_ERROR] Could not create MQL5/Files directory for account {account}")
            return False
        
        filename = f"webhook_command_{int(time.time())}.json"
        filepath = os.path.join(files_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(command, f, ensure_ascii=False, indent=2)
        
        logger.info(f"[FILE_WRITTEN] Command written to {filepath}")
        return True
        
    except Exception as e:
        logger.error(f"[FILE_WRITE_ERROR] Account {account}: {str(e)}")
        return False

@app.route('/diagnose')
@session_login_required
def diagnose_system():
    try:
        diagnosis = session_manager.diagnose_profile_source()
        
        return jsonify({
            'profile_source': session_manager.profile_source,
            'instances_dir': session_manager.instances_dir,
            'mt5_path': session_manager.mt5_path,
            'diagnosis': diagnosis
        })
        
    except Exception as e:
        logger.error(f"[DIAGNOSE] Failed to diagnose system: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logger.info("[STARTING] Trading Bot Server")
    logger.info(f"[CONFIG] Webhook endpoint: /webhook/{WEBHOOK_TOKEN}")
    logger.info(f"[CONFIG] External URL: {EXTERNAL_BASE_URL}")
    logger.info(f"[CONFIG] Supported actions: BUY, SELL, LONG, SHORT, CLOSE, CLOSE_ALL, CLOSE_SYMBOL")
    
    # ✅ Initialize trade history
    with app.app_context():
        init_trades()
    
    # Send startup notification
    email_handler.send_startup_notification()
    
    app.run(
        host='0.0.0.0',
        port=int(os.getenv('PORT', 5000)),
        debug=os.getenv('DEBUG', 'False').lower() == 'true'
    )
