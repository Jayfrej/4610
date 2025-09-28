import os
import smtplib
import logging
import traceback
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import threading
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class EmailHandler:
    """Email notification handler with comprehensive error reporting"""
    
    def __init__(self):
        self.enabled = os.getenv('EMAIL_ENABLED', 'False').lower() == 'true'
        
        # Simplified email configuration - just need sender email and password
        self.sender_email = os.getenv('SENDER_EMAIL', '').strip()
        self.sender_password = os.getenv('SENDER_PASSWORD', '').strip()
        
        # Auto-detect SMTP settings based on email domain
        self.smtp_server, self.smtp_port = self._detect_smtp_settings()
        
        # Recipients (can be multiple, comma-separated)
        self.recipients = os.getenv('RECIPIENTS', '').strip()
        if self.recipients:
            self.to_emails = [email.strip() for email in self.recipients.split(',') if email.strip()]
        else:
            self.to_emails = []
        
        # Error tracking
        self.error_count = 0
        self.last_error_time = None
        
        if self.enabled:
            if not all([self.sender_email, self.sender_password, self.to_emails]):
                logger.warning("[EMAIL] Email enabled but missing configuration (SENDER_EMAIL, SENDER_PASSWORD, RECIPIENTS)")
                self.enabled = False
            else:
                logger.info(f"[EMAIL] Email notifications enabled")
                logger.info(f"[EMAIL] From: {self.sender_email}")
                logger.info(f"[EMAIL] To: {', '.join(self.to_emails)}")
                logger.info(f"[EMAIL] SMTP: {self.smtp_server}:{self.smtp_port}")
                
                # Set up error handler for all logging
                self._setup_error_handler()
        else:
            logger.info("[EMAIL] Email notifications disabled")
    
    def _setup_error_handler(self):
        """Set up custom logging handler to catch all errors"""
        class ErrorEmailHandler(logging.Handler):
            def __init__(self, email_handler):
                super().__init__(level=logging.ERROR)
                self.email_handler = email_handler
                
            def emit(self, record):
                if record.levelno >= logging.ERROR:
                    self.email_handler._handle_logging_error(record)
        
        # Add error handler to root logger to catch all errors
        error_handler = ErrorEmailHandler(self)
        logging.getLogger().addHandler(error_handler)
    
    def _handle_logging_error(self, record):
        """Handle errors from logging system"""
        try:
            error_msg = self.format(record)
            module_name = record.name
            
            # Get stack trace if available
            stack_trace = ""
            if record.exc_info:
                stack_trace = "\n\nStack Trace:\n" + "".join(traceback.format_exception(*record.exc_info))
            
            full_message = f"""
Error Details:
Module: {module_name}
Level: {record.levelname}
Message: {error_msg}
Time: {datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")}
Function: {record.funcName}
Line: {record.lineno}
{stack_trace}
            """
            
            self.send_error_alert(
                f"System Error in {module_name}",
                full_message.strip(),
                error_details={
                    'module': module_name,
                    'level': record.levelname,
                    'function': record.funcName,
                    'line': record.lineno
                }
            )
        except Exception as e:
            # Avoid infinite recursion if email sending fails
            print(f"[EMAIL] Failed to send error email: {e}")
    
    def _detect_smtp_settings(self):
        """Auto-detect SMTP settings based on sender email domain"""
        if not self.sender_email:
            return 'smtp.gmail.com', 587  # Default
        
        domain = self.sender_email.split('@')[1].lower() if '@' in self.sender_email else ''
        
        # Common email providers
        smtp_settings = {
            'gmail.com': ('smtp.gmail.com', 587),
            'outlook.com': ('smtp-mail.outlook.com', 587),
            'hotmail.com': ('smtp-mail.outlook.com', 587),
            'live.com': ('smtp-mail.outlook.com', 587),
            'yahoo.com': ('smtp.mail.yahoo.com', 587),
            'yahoo.co.th': ('smtp.mail.yahoo.com', 587),
            'icloud.com': ('smtp.mail.me.com', 587),
            'me.com': ('smtp.mail.me.com', 587),
        }
        
        settings = smtp_settings.get(domain, ('smtp.gmail.com', 587))  # Default to Gmail
        logger.info(f"[EMAIL] Detected SMTP settings for {domain}: {settings[0]}:{settings[1]}")
        return settings
    
    def send_alert(self, subject: str, message: str, priority: str = "normal"):
        """Send email alert asynchronously"""
        if not self.enabled:
            return
        
        # Send email in background thread to avoid blocking
        thread = threading.Thread(
            target=self._send_email_async,
            args=(subject, message, priority),
            daemon=True
        )
        thread.start()
    
    def send_error_alert(self, subject: str, message: str, error_details: Optional[Dict[str, Any]] = None, priority: str = "high"):
        """Send error-specific alert with enhanced formatting"""
        if not self.enabled:
            return
        
        self.error_count += 1
        self.last_error_time = datetime.now()
        
        # Enhanced error message format
        enhanced_message = f"""
🚨 ERROR ALERT #{self.error_count}

{message}

Error Summary:
- Error Count Today: {self.error_count}
- System Status: Requires Attention
- Severity: {priority.upper()}

Please check the system immediately.
        """
        
        # Use high priority for errors by default
        self.send_alert(f"🚨 {subject}", enhanced_message.strip(), priority)
    
    def send_exception_alert(self, exception: Exception, context: str = "", additional_info: Dict[str, Any] = None):
        """Send alert for caught exceptions with full details"""
        exc_type = type(exception).__name__
        exc_message = str(exception)
        
        # Get current stack trace
        stack_trace = traceback.format_exc()
        
        message = f"""
Exception occurred in the system:

Exception Type: {exc_type}
Exception Message: {exc_message}
Context: {context}

Stack Trace:
{stack_trace}
        """
        
        if additional_info:
            message += "\nAdditional Information:\n"
            for key, value in additional_info.items():
                message += f"- {key}: {value}\n"
        
        self.send_error_alert(
            f"Exception: {exc_type}",
            message.strip(),
            error_details={
                'exception_type': exc_type,
                'exception_message': exc_message,
                'context': context
            }
        )
    
    def send_mt5_error_alert(self, account: str, operation: str, error_code: int = None, error_message: str = ""):
        """Send MT5-specific error alert"""
        message = f"""
MT5 Trading Error Detected:

Account: {account}
Operation: {operation}
Error Code: {error_code if error_code else 'Unknown'}
Error Message: {error_message}
Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

This error occurred during trading operations and requires immediate attention.
        """
        
        self.send_error_alert(
            f"MT5 Error - {operation} Failed",
            message.strip(),
            error_details={
                'account': account,
                'operation': operation,
                'error_code': error_code,
                'error_message': error_message
            }
        )
    
    def send_webhook_error_alert(self, error_type: str, error_message: str, payload_data: Dict[str, Any] = None):
        """Send webhook-specific error alert"""
        message = f"""
Webhook Processing Error:

Error Type: {error_type}
Error Message: {error_message}
Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        """
        
        if payload_data:
            message += f"\nPayload Data:\n{payload_data}"
        
        self.send_error_alert(
            f"Webhook Error - {error_type}",
            message.strip(),
            error_details={
                'error_type': error_type,
                'error_message': error_message,
                'payload': payload_data
            }
        )
    
    def send_connection_error_alert(self, service: str, error_message: str, retry_count: int = 0):
        """Send connection error alert"""
        message = f"""
Connection Error Detected:

Service: {service}
Error: {error_message}
Retry Count: {retry_count}
Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

The system is having trouble connecting to {service}.
        """
        
        self.send_error_alert(
            f"Connection Error - {service}",
            message.strip(),
            error_details={
                'service': service,
                'error_message': error_message,
                'retry_count': retry_count
            }
        )
    
    def _send_email_async(self, subject: str, message: str, priority: str = "normal"):
        """Send email in background thread"""
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = ', '.join(self.to_emails)
            msg['Subject'] = f"[MT5 Trading Bot] {subject}"
            
            # Add priority header
            if priority == "high":
                msg['X-Priority'] = '1'
                msg['X-MSMail-Priority'] = 'High'
            elif priority == "low":
                msg['X-Priority'] = '5'
                msg['X-MSMail-Priority'] = 'Low'
            
            # Create HTML and text versions
            html_body = self._create_html_body(subject, message)
            text_body = self._create_text_body(subject, message)
            
            msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))
            
            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                
                for to_email in self.to_emails:
                    server.send_message(msg, self.sender_email, [to_email])
            
            logger.info(f"[EMAIL] Alert sent successfully: {subject}")
            
        except Exception as e:
            # Use print instead of logger to avoid recursion
            print(f"[EMAIL] Failed to send alert: {str(e)}")
    
    def _create_html_body(self, subject: str, message: str) -> str:
        """Create HTML email body with enhanced error styling"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Determine alert color and icon based on subject
        if any(word in subject.lower() for word in ['error', 'failed', 'exception', '🚨', 'unauthorized', 'offline']):
            alert_color = '#dc3545'  # Red
            alert_type = 'Error'
            alert_icon = '🚨'
        elif any(word in subject.lower() for word in ['warning', 'bad payload']):
            alert_color = '#ffc107'  # Yellow
            alert_type = 'Warning'
            alert_icon = '⚠️'
        elif any(word in subject.lower() for word in ['online', 'success', 'added', 'startup']):
            alert_color = '#28a745'  # Green
            alert_type = 'Success'
            alert_icon = '✅'
        else:
            alert_color = '#007bff'  # Blue
            alert_type = 'Info'
            alert_icon = 'ℹ️'
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .alert {{ padding: 20px; border-radius: 5px; margin-bottom: 20px; border-left: 6px solid {alert_color}; background-color: {alert_color}15; }}
                .alert-title {{ font-weight: bold; color: {alert_color}; margin-bottom: 10px; font-size: 18px; }}
                .content {{ line-height: 1.6; color: #333; }}
                .error-content {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; font-family: monospace; white-space: pre-wrap; margin: 10px 0; }}
                .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #666; text-align: center; }}
                .timestamp {{ color: #999; font-size: 14px; }}
                .error-stats {{ background-color: #fff3cd; padding: 10px; border-radius: 5px; margin: 10px 0; border-left: 4px solid #ffc107; }}
                pre {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2 style="color: #333; margin: 0;">{alert_icon} MT5 Trading Bot Alert</h2>
                </div>
                
                <div class="alert">
                    <div class="alert-title">{alert_icon} {alert_type}: {subject}</div>
                    <div class="timestamp">{timestamp}</div>
                </div>
                
                {f'<div class="error-stats">Total Errors Today: {self.error_count}</div>' if self.error_count > 0 else ''}
                
                <div class="content">
                    <div class="error-content">{message}</div>
                </div>
                
                <div class="footer">
                    <p><strong>This is an automated error alert from your MT5 Trading Bot system.</strong></p>
                    <p>Please check your system immediately if this is an error notification.</p>
                    <p>Server time: {timestamp}</p>
                </div>
            </div>
        </body>
        </html>
        """
        return html
    
    def _create_text_body(self, subject: str, message: str) -> str:
        """Create plain text email body"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        text = f"""
🤖 MT5 Trading Bot Alert
{"=" * 60}

Subject: {subject}
Time: {timestamp}
{f"Total Errors Today: {self.error_count}" if self.error_count > 0 else ""}

Message:
{message}

{"=" * 60}
This is an automated message from your MT5 Trading Bot system.
Please check your system immediately if this is an error notification.
        """
        return text.strip()
    
    def send_startup_notification(self):
        """Send notification when bot starts"""
        message = f"""
Trading Bot Server has started successfully.

Configuration:
- Server Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- Email Notifications: {'Enabled' if self.enabled else 'Disabled'}
- Error Monitoring: {'Active' if self.enabled else 'Inactive'}
- Webhook Endpoint: Available
- Instance Manager: Initialized

The system is ready to receive trading signals and close position commands.
All errors will be automatically reported via email.
        """
        self.send_alert("System Startup", message.strip(), "low")
    
    def send_shutdown_notification(self):
        """Send notification when bot shuts down"""
        message = f"""
Trading Bot Server is shutting down.

Shutdown Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Total Errors Handled: {self.error_count}

All active MT5 instances will remain running.
        """
        self.send_alert("System Shutdown", message.strip(), "low")
    
    def send_account_notification(self, account: str, action: str, details: str = ""):
        """Send account-related notification"""
        message = f"""
Account Action: {action}
Account: {account}
Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

{details}
        """
        self.send_alert(f"Account {action}", message.strip())
    
    def send_webhook_summary(self, success_count: int, total_count: int, details: str = ""):
        """Send webhook processing summary"""
        if success_count == total_count:
            subject = f"Webhook Success ({success_count}/{total_count})"
            priority = "low"
        elif success_count > 0:
            subject = f"Webhook Partial Success ({success_count}/{total_count})"
            priority = "normal"
        else:
            subject = f"Webhook Failed ({success_count}/{total_count})"
            priority = "high"
        
        message = f"""
Webhook Processing Summary
Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Results: {success_count} successful out of {total_count} accounts

{details}
        """
        self.send_alert(subject, message.strip(), priority)
    
    def test_email_config(self) -> bool:
        """Test email configuration"""
        if not self.enabled:
            logger.info("[EMAIL] Email not enabled, skipping test")
            return True
        
        try:
            test_message = f"""
This is a test email from your MT5 Trading Bot system.

Configuration Test Results:
- SMTP Server: {self.smtp_server}:{self.smtp_port}
- From Email: {self.sender_email}
- To Emails: {', '.join(self.to_emails)}
- Test Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- Error Monitoring: Active

If you receive this email, your email configuration is working correctly.
All system errors will be automatically reported to this email address.
            """
            
            self.send_alert("Email Configuration Test", test_message.strip(), "low")
            logger.info("[EMAIL] Test email sent")
            return True
            
        except Exception as e:
            logger.error(f"[EMAIL] Test email failed: {str(e)}")
            return False
    
    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics"""
        return {
            'total_errors': self.error_count,
            'last_error_time': self.last_error_time.isoformat() if self.last_error_time else None,
            'email_enabled': self.enabled
        }


# Convenience function for easy error reporting from other modules
def report_error(exception: Exception, context: str = "", additional_info: Dict[str, Any] = None):
    """Global function to report errors - can be used from anywhere in the application"""
    try:
        # Try to get the global email handler instance
        if hasattr(report_error, '_email_handler'):
            report_error._email_handler.send_exception_alert(exception, context, additional_info)
        else:
            # Fallback logging
            logger.error(f"Error in {context}: {exception}", exc_info=True)
    except Exception as e:
        logger.error(f"Failed to report error: {e}")


# Global initialization function
def init_global_error_reporting(email_handler: EmailHandler):
    """Initialize global error reporting"""
    report_error._email_handler = email_handler


# Usage Example:
"""
# In your main application file:

from email_handler import EmailHandler, init_global_error_reporting, report_error

# Initialize email handler
email_handler = EmailHandler()

# Set up global error reporting
init_global_error_reporting(email_handler)

# Now you can report errors from anywhere:
try:
    # Some risky operation
    pass
except Exception as e:
    report_error(e, "main_trading_loop", {"account": "12345", "symbol": "EURUSD"})

# Or use specific error methods:
email_handler.send_mt5_error_alert("12345", "place_order", 10006, "Invalid volume")
email_handler.send_webhook_error_alert("invalid_payload", "Missing required field 'symbol'", payload_data)
"""
