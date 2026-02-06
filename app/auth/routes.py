from flask import request, jsonify
from flask_jwt_extended import (
    create_access_token, 
    create_refresh_token, 
    jwt_required, 
    get_jwt_identity,
    get_jwt
)
from app.auth import bp
from app.models.user import User
from app import bcrypt
from datetime import datetime


@bp.route('/login', methods=['POST'])
def login():
    """Admin login with username and password"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    username = data.get('username', '').strip()
    password = data.get('password', '')
    
    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400
    
    # Find user by username
    user = User.find_by_username(username)
    
    if not user:
        return jsonify({'error': 'Invalid username or password'}), 401
    
    # Verify password (handle both hashed and pre-hashed passwords)
    password_valid = False
    
    # First try direct bcrypt comparison
    if user.get('password'):
        try:
            password_valid = bcrypt.check_password_hash(user['password'], password)
        except Exception:
            pass
    
    if not password_valid:
        return jsonify({'error': 'Invalid username or password'}), 401
    
    # Create tokens
    user_id = str(user['_id'])
    additional_claims = {
        'user_type': user.get('user_type', 'admin'),
        'username': user.get('username'),
        'full_name': user.get('full_name', '')
    }
    
    access_token = create_access_token(identity=user_id, additional_claims=additional_claims)
    refresh_token = create_refresh_token(identity=user_id, additional_claims=additional_claims)
    
    return jsonify({
        'message': 'Login successful',
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': {
            'id': user_id,
            'username': user.get('username'),
            'full_name': user.get('full_name', ''),
            'user_type': user.get('user_type', 'admin')
        }
    }), 200


@bp.route('/admin-login', methods=['POST'])
def admin_login():
    """Admin login route (alias for /login)"""
    return login()


@bp.route('/exam-login', methods=['POST'])
def exam_login():
    """Student exam login using admission number only"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    admission_number = data.get('admission_number', '').strip()
    
    if not admission_number:
        return jsonify({'error': 'Admission number is required'}), 400
    
    # Find student by admission number (case-insensitive)
    student = User.find_by_admission_number_ci(admission_number)
    
    if not student:
        return jsonify({'error': 'Student not found. Please check your admission number.'}), 401
    
    if student.get('user_type') != 'student':
        return jsonify({'error': 'Invalid account type'}), 401
    
    # Create exam mode tokens
    student_id = str(student['_id'])
    additional_claims = {
        'user_type': 'student_exam',
        'admission_number': student.get('admission_number'),
        'full_name': student.get('full_name', ''),
        'class_id': student.get('class_id', '')
    }
    
    access_token = create_access_token(identity=student_id, additional_claims=additional_claims)
    refresh_token = create_refresh_token(identity=student_id, additional_claims=additional_claims)
    
    return jsonify({
        'message': 'Exam login successful',
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': {
            'id': student_id,
            'admission_number': student.get('admission_number'),
            'full_name': student.get('full_name', ''),
            'class_id': student.get('class_id', ''),
            'user_type': 'student_exam'
        }
    }), 200


@bp.route('/student-exam-login', methods=['POST'])
def student_exam_login():
    """
    Student exam login with admission number and password.
    Password can be any part of their name (for simple auth).
    """
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    admission_number = data.get('admission_number', '').strip()
    password = data.get('password', '').strip()
    
    if not admission_number:
        return jsonify({'error': 'Admission number is required'}), 400
    
    # Verify student using admission number and name-based password
    student = User.verify_student_admission_surname_login(admission_number, password)
    
    if not student:
        return jsonify({'error': 'Invalid admission number or password'}), 401
    
    # Create exam mode tokens
    student_id = str(student['_id'])
    additional_claims = {
        'user_type': 'student_exam',
        'admission_number': student.get('admission_number'),
        'full_name': student.get('full_name', ''),
        'class_id': student.get('class_id', '')
    }
    
    access_token = create_access_token(identity=student_id, additional_claims=additional_claims)
    refresh_token = create_refresh_token(identity=student_id, additional_claims=additional_claims)
    
    return jsonify({
        'message': 'Exam login successful',
        'access_token': access_token,
        'refresh_token': refresh_token,
        'user': {
            'id': student_id,
            'admission_number': student.get('admission_number'),
            'full_name': student.get('full_name', ''),
            'class_id': student.get('class_id', ''),
            'user_type': 'student_exam'
        }
    }), 200


@bp.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """Refresh access token"""
    identity = get_jwt_identity()
    claims = get_jwt()
    
    additional_claims = {
        'user_type': claims.get('user_type'),
        'username': claims.get('username'),
        'full_name': claims.get('full_name'),
        'admission_number': claims.get('admission_number'),
        'class_id': claims.get('class_id')
    }
    
    access_token = create_access_token(identity=identity, additional_claims=additional_claims)
    
    return jsonify({
        'access_token': access_token
    }), 200


@bp.route('/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """Get current user information"""
    user_id = get_jwt_identity()
    claims = get_jwt()
    
    user = User.find_by_id(user_id)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    user_data = {
        'id': str(user['_id']),
        'username': user.get('username'),
        'full_name': user.get('full_name', ''),
        'user_type': claims.get('user_type', user.get('user_type'))
    }
    
    # Add student-specific fields
    if user.get('user_type') == 'student' or claims.get('user_type') == 'student_exam':
        user_data['admission_number'] = user.get('admission_number')
        user_data['class_id'] = user.get('class_id')
    
    return jsonify({'user': user_data}), 200


@bp.route('/logout', methods=['POST'])
@jwt_required()
def logout():
    """Logout (token invalidation would be handled client-side)"""
    return jsonify({'message': 'Logout successful'}), 200
