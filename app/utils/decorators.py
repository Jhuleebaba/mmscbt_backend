from functools import wraps
from flask import jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from app.models.user import User


def login_required(f):
    """Basic login required decorator"""
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function


def role_required(*allowed_roles):
    """Decorator to check if user has required role"""
    def decorator(f):
        @wraps(f)
        @jwt_required()
        def decorated_function(*args, **kwargs):
            try:
                claims = get_jwt()
                user_type = claims.get('user_type')
                
                if user_type not in allowed_roles:
                    return jsonify({
                        'error': 'Access denied. Insufficient permissions.'
                    }), 403
                
                return f(*args, **kwargs)
            except Exception as e:
                return jsonify({'error': str(e)}), 500
        
        return decorated_function
    return decorator


def admin_required(f):
    """Decorator for admin-only routes"""
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        try:
            claims = get_jwt()
            user_type = claims.get('user_type')
            
            if user_type != 'admin':
                return jsonify({
                    'error': 'Access denied. Admin privileges required.'
                }), 403
            
            return f(*args, **kwargs)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    return decorated_function


def exam_mode_required(f):
    """Decorator for exam mode routes (student taking exam)"""
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        try:
            claims = get_jwt()
            user_type = claims.get('user_type')
            
            if user_type != 'student_exam':
                return jsonify({
                    'error': 'Access denied. Exam mode required.'
                }), 403
            
            return f(*args, **kwargs)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    return decorated_function


def get_current_user_data():
    """Helper function to get current user data from token"""
    try:
        user_id = get_jwt_identity()
        claims = get_jwt()
        
        return {
            'id': user_id,
            'user_type': claims.get('user_type'),
            'username': claims.get('username'),
            'full_name': claims.get('full_name'),
            'admission_number': claims.get('admission_number'),
            'class_id': claims.get('class_id')
        }
    except Exception:
        return None
