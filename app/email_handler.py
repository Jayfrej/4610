import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import threading

logger = logging.getLogger(__name__)

class EmailHandler:
    """Email notification handler"""
    
    def __init__(self):
        self.enabled = os.getenv('EMAIL_ENABLED', 'False').lower() == 'true'
        self.smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_user = os.getenv('SMTP_USER', '')
        self.smtp_pass = os.getenv('SMTP_PASS', '')
        self.from_email = os.getenv('FROM_EMAIL', self.smtp_user)
        self.to_emails = os.getenv('TO_EMAILS', '').split(',')
        self.to_emails = [email.strip() for email in self.to_emails if email.strip()]
        
        if self.enabled:
            if not all([self.smtp_user, self.smtp_pass, self.to_emails]):
                logger.warning("[EMAIL] Email enabled but missing configuration")
                self.enabled = False
            else:
                logger.info(f"[EMAIL] Email notifications enabled, sending to: {', '.join(self.to_emails)}")
        else:
            logger.info("[EMAIL] Email notifications disabled")
    
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
    
    def _send_email_async(self, subject: str, message: str, priority: str = "normal"):
        """Send email in background thread"""
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.from_email
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
                server.login(self.smtp_user, self.smtp_pass)
                
                for to_email in self.to_emails:
                    server.send_message(msg, self.from_email, [to_email])
            
            logger.info(f"[EMAIL] Alert sent successfully: {subject}")
            
        except Exception as e:
            logger.error(f"[EMAIL] Failed to send alert: {str(e)}")
    
    def _create_html_body(self, subject: str, message: str) -> str:
        """Create HTML email body"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Determine alert color based on subject
        if any(word in subject.lower() for word in ['error', 'failed', 'unauthorized', 'offline']):
            alert_color = '#dc3545'  # Red
            alert_type = 'Error'
        elif any(word in subject.lower() for word in ['warning', 'bad payload']):
            alert_color = '#ffc107'  # Yellow
            alert_type = 'Warning'
        elif any(word in subject.lower() for word in ['online', 'success', 'added']):
            alert_color = '#28a745'  # Green
            alert_type = 'Success'
        else:
            alert_color = '#007bff'  # Blue
            alert_type = 'Info'
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .alert {{ padding: 15px; border-radius: 5px; margin-bottom: 20px; border-left: 4px solid {alert_color}; background-color: {alert_color}15; }}
                .alert-title {{ font-weight: bold; color: {alert_color}; margin-bottom: 10px; }}
                .content {{ line-height: 1.6; color: #333; }}
                .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #666; text-align: center; }}
                .timestamp {{ color: #999; font-size: 14px; }}
                pre {{ background-color: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2 style="color: #333; margin: 0;">🤖 MT5 Trading Bot Alert</h2>
                </div>
                
                <div class="alert">
                    <div class="alert-title">{alert_type}: {subject}</div>
                    <div class="timestamp">{timestamp}</div>
                </div>
                
                <div class="content">
                    <pre>{message}</pre>
                </div>
                
                <div class="footer">
                    <p>This is an automated message from your MT5 Trading Bot system.</p>
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
MT5 Trading Bot Alert
{"=" * 50}

Subject: {subject}
Time: {timestamp}

Message:
{message}

{"=" * 50}
This is an automated message from your MT5 Trading Bot system.
        """
        return text.strip()
    
    def send_startup_notification(self):
        """Send notification when bot starts"""
        message = f"""
Trading Bot Server has started successfully.

Configuration:
- Server Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- Email Notifications: {'Enabled' if self.enabled else 'Disabled'}
- Webhook Endpoint: Available
- Instance Manager: Initialized

The system is ready to receive trading signals.
        """
        self.send_alert("System Startup", message.strip(), "low")
    
    def send_shutdown_notification(self):
        """Send notification when bot shuts down"""
        message = f"""
Trading Bot Server is shutting down.

Shutdown Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

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
- From Email: {self.from_email}
- To Emails: {', '.join(self.to_emails)}
- Test Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

If you receive this email, your email configuration is working correctly.
            """
            
            self.send_alert("Email Configuration Test", test_message.strip(), "low")
            logger.info("[EMAIL] Test email sent")
            return True
            
        except Exception as e:
            logger.error(f"[EMAIL] Test email failed: {str(e)}")
            return False