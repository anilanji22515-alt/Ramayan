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
    def send_notification(recipient, subject, body_text, body_html=None):
        """
        Sends an email using configured SMTP, or falls back to robust simulation.
        Returns a dict with status: 'SENT' | 'SIMULATED' | 'FAILED', message_id, error
        """
        message_id = f"MSG-{uuid.uuid4().hex[:12].upper()}"
        
        # Check if actual SMTP is configured and enabled
        if Config.EMAIL_ENABLED and Config.SMTP_USER and Config.SMTP_PASSWORD:
            try:
                msg = MIMEMultipart('alternative')
                msg['Subject'] = subject
                msg['From'] = Config.EMAIL_FROM
                msg['To'] = recipient
                msg['Message-ID'] = f"<{message_id}@campuscare.edu>"
                msg['Date'] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
                
                part1 = MIMEText(body_text, 'plain')
                msg.attach(part1)
                if body_html:
                    part2 = MIMEText(body_html, 'html')
                    msg.attach(part2)
                
                with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=10) as server:
                    server.starttls()
                    server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
                    server.sendmail(Config.EMAIL_FROM, [recipient], msg.as_string())
                
                logger.info(f"Email sent successfully to {recipient} [{message_id}]")
                return {
                    'status': 'SENT',
                    'message_id': message_id,
                    'error': None,
                    'is_simulated': False
                }
            except Exception as e:
                logger.error(f"Failed to send real email to {recipient}: {str(e)}")
                return {
                    'status': 'FAILED',
                    'message_id': message_id,
                    'error': str(e),
                    'is_simulated': False
                }
        else:
            # Fallback to simulated delivery for prototype demo
            logger.info(f"[SIMULATION] Email prepared for {recipient}: '{subject}' [{message_id}]")
            return {
                'status': 'SIMULATED',
                'message_id': message_id,
                'error': None,
                'is_simulated': True,
                'note': 'Email simulation active - SMTP credentials not configured. Recorded in delivery outbox.'
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
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #1e293b; margin: 0; padding: 20px; }}
    .card {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); }}
    .header {{ background: linear-gradient(135deg, #2563eb, #1d4ed8); color: #ffffff; padding: 24px; text-align: left; }}
    .header h1 {{ margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -0.025em; }}
    .content {{ padding: 24px; }}
    .badge {{ display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; text-transform: uppercase; }}
    .badge-emergency {{ background-color: #fee2e2; color: #991b1b; }}
    .badge-high {{ background-color: #ffedd5; color: #9a3412; }}
    .badge-medium {{ background-color: #fef3c7; color: #92400e; }}
    .badge-low {{ background-color: #e0f2fe; color: #075985; }}
    .info-table {{ width: 100%; border-collapse: collapse; margin-top: 16px; margin-bottom: 20px; }}
    .info-table td {{ padding: 10px 12px; border-bottom: 1px solid #f1f5f9; font-size: 14px; }}
    .info-table td.label {{ color: #64748b; font-weight: 500; width: 35%; }}
    .info-table td.value {{ color: #0f172a; font-weight: 600; }}
    .summary-box {{ background: #f8fafc; border-left: 4px solid #3b82f6; padding: 14px; border-radius: 4px; font-size: 14px; color: #334155; margin-bottom: 20px; }}
    .footer {{ background: #f8fafc; padding: 16px 24px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #64748b; text-align: center; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <h1>CampusCare Portal Notification</h1>
      <p style="margin: 4px 0 0 0; opacity: 0.9; font-size: 14px;">Campus Problem Reporting & Management System</p>
    </div>
    <div class="content">
      <p style="margin-top: 0;">Hello,</p>
      <p>A new campus problem report has been submitted through <strong>CampusCare</strong>.</p>
      
      <table class="info-table">
        <tr>
          <td class="label">Complaint Reference</td>
          <td class="value"><span style="font-family: monospace; font-size: 15px; color: #2563eb;">{complaint_code}</span></td>
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
          <td class="value"><span style="color: #0284c7; font-weight: 700;">SUBMITTED</span></td>
        </tr>
      </table>

      <div class="summary-box">
        <strong>Issue Summary:</strong><br>
        {summary}
      </div>

      <p style="font-size: 13px; color: #64748b;">
        Please use the college-approved process or authorized secure portal to review updates and timeline progress.
      </p>
    </div>
    <div class="footer">
      This is an automated notification generated by CampusCare.<br>
      Please do not reply directly to this email.
    </div>
  </div>
</body>
</html>
"""
        return subject, body_text, body_html
