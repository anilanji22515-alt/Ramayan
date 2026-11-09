import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'campuscare-secret-key-production-dev-2026')
    DATABASE_PATH = os.environ.get('DATABASE_PATH', os.path.join(os.path.dirname(__file__), 'campuscare.db'))
    PARENT_NOTIFICATION_EMAIL = os.environ.get('PARENT_NOTIFICATION_EMAIL', 'anilanji22515@gmail.com')
    
    # SMTP Email Configuration
    EMAIL_ENABLED = os.environ.get('EMAIL_ENABLED', 'false').lower() in ('true', '1', 'yes')
    SMTP_HOST = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
    SMTP_USER = os.environ.get('SMTP_USER', '')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
    EMAIL_FROM = os.environ.get('EMAIL_FROM', 'campuscare-noreply@college.edu')
    
    # Upload Settings
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'pdf'}
    
    # Campus Information
    CAMPUS_NAME = "Main Campus - College of Engineering & Technology"
    TIMEZONE = "Asia/Kolkata"
