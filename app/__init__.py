from flask import Flask
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from pymongo import MongoClient
from config import config
import os
from datetime import datetime

# Initialize extensions
jwt = JWTManager()
cors = CORS()
bcrypt = Bcrypt()

# MongoDB client will be initialized in create_app
mongo_client = None
mongo_db = None


class MongoWrapper:
    """Simple wrapper to provide Flask-PyMongo-like interface"""
    @property
    def db(self):
        return mongo_db
    
    @property
    def cx(self):
        return mongo_client


# Create global mongo object for compatibility
mongo = MongoWrapper()


def create_app(config_name=None):
    """Application factory pattern"""
    global mongo_client, mongo_db
    app = Flask(__name__)
    
    # Load configuration
    config_name = config_name or os.environ.get('FLASK_ENV', 'default')
    app.config.from_object(config[config_name])
    
    # Initialize MongoDB
    try:
        mongo_uri = app.config.get('MONGO_URI') or os.environ.get('MONGO_URI', 'mongodb://localhost:27017')
        db_name = app.config.get('MONGO_DBNAME') or os.environ.get('MONGO_DBNAME', 'cbt_exam_database')
        
        # Ensure database name is in URI
        if db_name not in mongo_uri:
            if '?' in mongo_uri:
                base_part, query_part = mongo_uri.split('?', 1)
                mongo_uri = f"{base_part.rstrip('/')}/{db_name}?{query_part}"
            else:
                mongo_uri = f"{mongo_uri.rstrip('/')}/{db_name}"
        
        mongo_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        # Test connection
        mongo_client.admin.command('ping')
        mongo_db = mongo_client[db_name]
        app.logger.info(f"[OK] MongoDB connected: {db_name}")
    except Exception as e:
        app.logger.error(f"[ERROR] MongoDB connection failed: {e}")
        mongo_client = None
        mongo_db = None
    
    # Initialize extensions
    jwt.init_app(app)
    bcrypt.init_app(app)
    
    # Register blueprints
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    
    from app.admin import bp as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    
    from app.examinations import bp as examinations_bp
    app.register_blueprint(examinations_bp, url_prefix='/api/examinations')

    from app.settings import bp as settings_bp
    app.register_blueprint(settings_bp, url_prefix='/api/settings')
    
    # Register bulk upload blueprint (with graceful fallback if deps missing)
    try:
        from app.admin.bulk_upload import bp as bulk_upload_bp
        app.register_blueprint(bulk_upload_bp, url_prefix='/api')
        app.logger.info('[OK] Bulk upload module registered')
    except ImportError as e:
        app.logger.warning(f'[WARN] Bulk upload module not available: {e}')
    
    # Apply CORS
    CORS(app, resources={r"/api/*": {
        "origins": app.config['CORS_ORIGINS'],
        "allow_headers": app.config['CORS_ALLOW_HEADERS'],
        "methods": app.config['CORS_METHODS'],
        "supports_credentials": app.config['CORS_SUPPORTS_CREDENTIALS']
    }})
    
    # Initialize database with default admin
    try:
        with app.app_context():
            from app.utils.init_db import initialize_database
            initialize_database()
    except Exception as e:
        app.logger.error(f'[ERROR] Database initialization failed: {e}')
    
    @app.route('/')
    def index():
        return {
            'message': 'CBT Exam System API',
            'status': 'active',
            'version': '1.0.0',
            'frontend_url': app.config['FRONTEND_URL']
        }
    
    @app.route('/api/health')
    def health_check():
        db_status = 'connected' if mongo_db is not None else 'disconnected'
        return {
            'status': 'healthy',
            'database': db_status,
            'timestamp': datetime.utcnow().isoformat()
        }
    
    app.logger.info('[OK] CBT Exam System API ready')
    return app
