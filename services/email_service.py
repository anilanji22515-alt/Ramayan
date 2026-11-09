import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
import uuid
import logging
from config import Config

logger = logging.getLogger('campuscare.email')

class EmailService:
    @staticmethod
    def get_smtp_settings():
        """
        Retrieves current SMTP and recipient settings, merging environment
        defaults with any dynamic overrides stored in system_settings.
        """
        settings = {
            'enabled': Config.EMAIL_ENABLED,
            'host': Config.SMTP_HOST,
            'port': Config.SMTP_PORT,
            'user': Config.SMTP_USER,
            'password': Config.SMTP_PASSWORD,
            'from_email': Config.EMAIL_FROM,
            'recipient': Config.PARENT_NOTIFICATION_EMAIL
        }
        
        try:
            from database import get_db
            conn = get_db()
            rows = conn.execute("SELECT setting_key, setting_value FROM system_settings").fetchall()
            conn.close()
            for r in rows:
                k = r['setting_key']
                v = r['setting_value']
                if k == 'EMAIL_ENABLED':
                    settings['enabled'] = v.lower() in ('true', '1', 'yes')
                elif k == 'SMTP_HOST':
                    settings['host'] = v
                elif k == 'SMTP_PORT':
                    settings['port'] = int(v) if v.isdigit() else 587
                elif k == 'SMTP_USER':
                    settings['user'] = v
                elif k == 'SMTP_PASSWORD':
                    settings['password'] = v
                elif k == 'EMAIL_FROM':
                    settings['from_email'] = v
                elif k == 'PARENT_NOTIFICATION_EMAIL':
                    settings['recipient'] = v
        except Exception as e:
            logger.debug(f"Could not read database system_settings: {e}")
            
        return settings

    @staticmethod
    def send_notification(recipient, subject, body_text, body_html=None, override_settings=None):
        """
        Sends an email using configured SMTP, or falls back to robust simulation.
        Returns a dict with status: 'SENT' | 'SIMULATED' | 'FAILED', message_id, error, note.
        """
        cfg = override_settings or EmailService.get_smtp_settings()
        message_id = f"MSG-{uuid.uuid4().hex[:12].upper()}"
        
        # Check if actual SMTP credentials are provided and email sending is enabled
        smtp_user = cfg.get('user', '').strip()
        smtp_pass = cfg.get('password', '').strip()
        smtp_host = cfg.get('host', 'smtp.gmail.com').strip()
        smtp_port = int(cfg.get('port', 587))
        from_addr = cfg.get('from_email', '').strip() or smtp_user or 'campuscare-noreply@college.edu'
        is_enabled = cfg.get('enabled', False)
        
        if is_enabled and smtp_user and smtp_pass:
            try:
                msg = MIMEMultipart('alternative')
                msg['Subject'] = subject
                msg['From'] = f"CampusCare Problem Portal <{from_addr}>"
                msg['To'] = recipient
                msg['Message-ID'] = f"<{message_id}@campuscare.edu>"
                msg['Date'] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
                
                part1 = MIMEText(body_text, 'plain')
                msg.attach(part1)
                if body_html:
                    part2 = MIMEText(body_html, 'html')
                    msg.attach(part2)
                
                # Support direct SSL (port 465) or STARTTLS (port 587 / 25)
                if smtp_port == 465:
                    with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=12) as server:
                        server.login(smtp_user, smtp_pass)
                        server.sendmail(from_addr, [recipient], msg.as_string())
                else:
                    with smtplib.SMTP(smtp_host, smtp_port, timeout=12) as server:
                        server.ehlo()
                        server.starttls()
                        server.ehlo()
                        server.login(smtp_user, smtp_pass)
                        server.sendmail(from_addr, [recipient], msg.as_string())
                
                logger.info(f"Live email delivered successfully to {recipient} [{message_id}] via {smtp_host}:{smtp_port}")
                return {
                    'status': 'SENT',
                    'message_id': message_id,
                    'error': None,
                    'is_simulated': False,
                    'note': f"Live email delivered to {recipient} via {smtp_host}"
                }
            except Exception as e:
                err_msg = str(e)
                logger.error(f"Live SMTP delivery failed for {recipient}: {err_msg}")
                return {
                    'status': 'FAILED',
                    'message_id': message_id,
                    'error': err_msg,
                    'is_simulated': False,
                    'note': f"SMTP Error: {err_msg}. Please check SMTP credentials in Admin > Email Configuration."
                }
        else:
            # Fallback to simulated delivery for prototype demo
            logger.info(f"[SIMULATION] Email recorded in outbox for {recipient}: '{subject}' [{message_id}]")
            return {
                'status': 'SIMULATED',
                'message_id': message_id,
                'error': None,
                'is_simulated': True,
                'note': f"Delivery recorded in outbox for {recipient}. (To dispatch live internet emails, enter your SMTP App Password in the Admin Email Configuration panel or set SMTP_USER and SMTP_PASSWORD in .env)."
            }

    @staticmethod
    def format_complaint_email(complaint_code, category, priority, location, summary, submitted_at):
        """
        Formats standard parent/guardian notification email adhering to privacy guidelines.
        """
        subject = f"CampusCare: New campus complaint submitted - {complaint_code}"
        
        body_text = f"""Hello,

A new campus problem report has been submitted through CampusCare.

Complaint ID: {complaint_code}
Category: {category}
Priority: {priority}
Location: {location}
Submitted on: {submitted_at}
Summary: {summary}
Current status: Submitted

Please use the college-approved process or secure portal to view authorized details.

This is an automated notification. Please do not reply to this email.
"""
        
        body_html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #fff7ed; color: #1e293b; margin: 0; padding: 20px; }}
    .card {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 16px; border: 1px solid #fed7aa; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(249, 115, 22, 0.08); }}
    .header {{ background: linear-gradient(135deg, #ea580c, #f97316); color: #ffffff; padding: 24px; text-align: left; }}
    .header h1 {{ margin: 0; font-size: 20px; font-weight: 700; }}
    .content {{ padding: 24px; }}
    .info-table {{ width: 100%; border-collapse: collapse; margin-top: 16px; margin-bottom: 20px; }}
    .info-table td {{ padding: 10px 12px; border-bottom: 1px solid #ffedd5; font-size: 14px; }}
    .info-table td.label {{ color: #78716c; font-weight: 500; width: 35%; }}
    .info-table td.value {{ color: #0c0a09; font-weight: 600; }}
    .summary-box {{ background: #fff7ed; border-left: 4px solid #f97316; padding: 14px; border-radius: 4px; font-size: 14px; color: #431407; margin-bottom: 20px; }}
    .footer {{ background: #fffaf5; padding: 16px 24px; border-top: 1px solid #fed7aa; font-size: 12px; color: #78716c; text-align: center; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h1>CampusCare Problem Notification</h1>
      <p style="margin: 4px 0 0 0; opacity: 0.95; font-size: 13px;">Automated Campus Notification System</p>
    </div>
    <div class="content">
      <p style="margin-top: 0;">Hello,</p>
      <p>A new campus problem report has been submitted through <strong>CampusCare</strong>.</p>
      
      <table class="info-table">
        <tr>
          <td class="label">Complaint Reference</td>
          <td class="value"><span style="font-family: monospace; font-size: 15px; color: #ea580c;">{complaint_code}</span></td>
        </tr>
        <tr>
          <td class="label">Category</td>
          <td class="value">{category}</td>
        </tr>
        <tr>
          <td class="label">Priority</td>
          <td class="value">{priority}</td>
        </tr>
        <tr>
          <td class="label">Location</td>
          <td class="value">{location}</td>
        </tr>
        <tr>
          <td class="label">Submitted Time</td>
          <td class="value">{submitted_at}</td>
        </tr>
        <tr>
          <td class="label">Current Status</td>
          <td class="value"><span style="color: #ea580c; font-weight: 700;">SUBMITTED</span></td>
        </tr>
      </table>

      <div class="summary-box">
        <strong>Issue Summary:</strong><br>
        {summary}
      </div>

      <p style="font-size: 13px; color: #78716c;">
        Please use the college-approved process or authorized secure portal to review updates and timeline progress.
      </p>
    </div>
    <div class="footer">
      This is an automated notification generated by CampusCare.<br>
      Target notification address: anilanji22515@gmail.com
    </div>
  </div>
</body>
</html>
"""
        return subject, body_text, body_html
