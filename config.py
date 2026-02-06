import os
import re
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'cbt-fallback-secret-key-change-in-production'
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'cbt-fallback-jwt-secret-change-in-production'
    
    # JWT token durations
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=4)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(minutes=30)
    
    # MongoDB Configuration
    # Prefer production URI (cloud) over local
    MONGO_URI = os.environ.get('MONGO_PRODUCTION_URI') or os.environ.get('MONGO_URI') or 'mongodb://localhost:27017'
    MONGO_DBNAME = os.environ.get('MONGO_DBNAME') or 'cbt_exam_database'
    
    # Build full MongoDB URI with database name
    if MONGO_URI and MONGO_DBNAME:
        if '?' in MONGO_URI:
            base_part, query_part = MONGO_URI.split('?', 1)
            base_part = base_part.rstrip('/')
            MONGO_URI = f"{base_part}/{MONGO_DBNAME}?{query_part}"
        else:
            MONGO_URI = f"{MONGO_URI.rstrip('/')}/{MONGO_DBNAME}"
    
    # Password Settings
    DEFAULT_ADMIN_PASSWORD = os.environ.get('DEFAULT_ADMIN_PASSWORD') or 'admin123'
    BCRYPT_LOG_ROUNDS = 12
    
    # Frontend Configuration
    FRONTEND_URL = os.environ.get('FRONTEND_URL') or 'http://localhost:3001'
    
    # CORS Configuration
    CORS_ORIGINS = [origin.strip() for origin in os.environ.get(
        'CORS_ORIGINS',
        'http://localhost:3001'
    ).split(',') if origin.strip()]
    
    # Allow common private LAN ranges during development
    LAN_REGEX_ORIGINS = [
        re.compile(r"^http://192\.168\.\d{1,3}\.\d{1,3}(:\d+)?$"),
        re.compile(r"^http://10\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d+)?$"),
        re.compile(r"^http://172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}(:\d+)?$")
    ]
    
    CORS_ORIGINS = [*CORS_ORIGINS, *LAN_REGEX_ORIGINS]
    
    CORS_ALLOW_HEADERS = [
        'Content-Type',
        'Authorization',
        'Access-Control-Allow-Credentials'
    ]
    CORS_METHODS = ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
    CORS_SUPPORTS_CREDENTIALS = True


class DevelopmentConfig(Config):
    DEBUG = True
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'cbt-dev-secret-key-not-for-production'
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'cbt-dev-jwt-secret-key-not-for-production'


class ProductionConfig(Config):
    DEBUG = False
    
    # Validate critical secrets in production
    def __init__(self):
        if not os.environ.get('SECRET_KEY'):
            raise ValueError("SECRET_KEY environment variable is required in production")
        if not os.environ.get('JWT_SECRET_KEY'):
            raise ValueError("JWT_SECRET_KEY environment variable is required in production")


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
