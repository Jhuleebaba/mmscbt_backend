from flask import request, jsonify
from bson import ObjectId
from app.admin import bp
from app import mongo
from app.models.user import User
from app.utils.decorators import admin_required
from app.utils.validators import validate_required_fields, sanitize_string
from app.utils.admission_helper import generate_admission_number
from datetime import datetime


@bp.route('/register-student', methods=['POST'])
@admin_required
def register_student():
    """Register a new student (Admin only)"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Validate required fields
    required_fields = ['full_name', 'class_id']
    is_valid, missing = validate_required_fields(data, required_fields)
    
    if not is_valid:
        return jsonify({'error': f'Missing required fields: {", ".join(missing)}'}), 400
    
    # Generate admission number if not provided
    admission_number = data.get('admission_number')
    if not admission_number:
        # Generate auto admission number
        admission_number = generate_admission_number(data['class_id'])
    else:
        # Validate manual input for collision
        existing = User.find_by_admission_number(admission_number)
        if existing:
            return jsonify({'error': f'Admission number {admission_number} already exists'}), 400
    
    # Double check for collision (safety)
    existing = User.find_by_admission_number(admission_number)
    if existing:
         # If auto-generated collision occurs (rare race condition), try generating again? 
         # Simpler to just fail and ask retry, or we could loop. 
         # For now, let's trust the gap filler but keep the safety check.
        return jsonify({'error': 'Admission number collision. Please try again.'}), 400
    
    # Parse full name into first and last name
    full_name = sanitize_string(data['full_name'])
    name_parts = full_name.split()
    first_name = name_parts[0] if name_parts else ''
    last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
    
    # Create student data
    student_data = {
        'admission_number': admission_number,
        'full_name': full_name,
        'first_name': first_name,
        'last_name': last_name,
        'class_id': data['class_id'],
        'user_type': 'student',
        'is_active': True,
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow()
    }
    
    # Add optional fields
    optional_fields = ['email', 'phone', 'date_of_birth', 'gender', 'address', 
                       'arm', 'parent_email', 'parent_phone', 'passport_picture']
    for field in optional_fields:
        if data.get(field):
            student_data[field] = data[field]
    
    # Insert student
    result = mongo.db.users.insert_one(student_data)
    student_data['_id'] = result.inserted_id
    
    return jsonify({
        'message': 'Student registered successfully',
        'student': {
            'id': str(student_data['_id']),
            'admission_number': admission_number,
            'full_name': full_name,
            'first_name': first_name,
            'last_name': last_name,
            'class_id': data['class_id']
        }
    }), 201


@bp.route('/users', methods=['GET'])
@admin_required
def get_users():
    """Get all users with pagination and filtering"""
    user_type = request.args.get('user_type', 'student')
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 50))
    class_filter = request.args.get('class_id')
    
    skip = (page - 1) * limit
    
    # Build query
    query = {'user_type': user_type, 'is_active': True}
    
    if class_filter:
        query['class_id'] = class_filter
    
    # Get users
    users = list(mongo.db.users.find(query).skip(skip).limit(limit).sort('created_at', -1))
    total = mongo.db.users.count_documents(query)
    
    # Serialize users
    serialized_users = []
    for user in users:
        serialized_user = {
            'id': str(user['_id']),
            'full_name': user.get('full_name', ''),
            'user_type': user.get('user_type', ''),
            'is_active': user.get('is_active', True),
            'created_at': user.get('created_at', datetime.utcnow()).isoformat() if user.get('created_at') else None
        }
        
        # Add type-specific fields
        if user_type == 'student':
            serialized_user['admission_number'] = user.get('admission_number', '')
            serialized_user['class_id'] = user.get('class_id', '')
            serialized_user['arm'] = user.get('arm', '')
        elif user_type == 'admin':
            serialized_user['username'] = user.get('username', '')
        
        serialized_users.append(serialized_user)
    
    return jsonify({
        'message': 'Users retrieved successfully',
        'users': serialized_users,
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total,
            'pages': (total + limit - 1) // limit
        }
    }), 200


@bp.route('/users/<user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    """Update a user (Admin only)"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Find user
    user = User.find_by_id(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Build update data
    update_data = {}
    
    # Allowed fields to update
    allowed_fields = ['full_name', 'class_id', 'arm', 'email', 'phone', 
                      'date_of_birth', 'gender', 'address', 'is_active']
    
    for field in allowed_fields:
        if field in data:
            update_data[field] = data[field]
    
    # Update first_name and last_name if full_name changed
    if 'full_name' in update_data:
        name_parts = update_data['full_name'].split()
        update_data['first_name'] = name_parts[0] if name_parts else ''
        update_data['last_name'] = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ''
    
    update_data['updated_at'] = datetime.utcnow()
    
    # Update user
    result = mongo.db.users.update_one(
        {'_id': ObjectId(user_id)},
        {'$set': update_data}
    )
    
    if result.modified_count == 0:
        return jsonify({'error': 'No changes made'}), 400
    
    # Get updated user
    updated_user = User.find_by_id(user_id)
    
    return jsonify({
        'message': 'User updated successfully',
        'user': {
            'id': str(updated_user['_id']),
            'full_name': updated_user.get('full_name', ''),
            'class_id': updated_user.get('class_id', ''),
            'user_type': updated_user.get('user_type', '')
        }
    }), 200


@bp.route('/users/<user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    """Delete a user (Admin only) - Hard delete"""
    user = User.find_by_id(user_id)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # Prevent deleting admin users for safety
    if user.get('user_type') == 'admin':
        return jsonify({'error': 'Cannot delete admin users'}), 400
    
    # Hard delete
    result = mongo.db.users.delete_one({'_id': ObjectId(user_id)})
    
    if result.deleted_count == 0:
        return jsonify({'error': 'Failed to delete user'}), 500
    
    return jsonify({'message': 'User deleted successfully'}), 200


@bp.route('/students-by-class/<class_name>', methods=['GET'])
@admin_required
def get_students_by_class(class_name):
    """Get all students in a specific class"""
    students = User.get_students_by_class(class_name)
    
    serialized_students = []
    for student in students:
        serialized_students.append({
            'id': str(student['_id']),
            'admission_number': student.get('admission_number', ''),
            'full_name': student.get('full_name', ''),
            'class_id': student.get('class_id', ''),
            'arm': student.get('arm', '')
        })
    
    return jsonify({
        'message': 'Students retrieved successfully',
        'students': serialized_students,
        'count': len(serialized_students)
    }), 200


@bp.route('/next-admission-number', methods=['GET'])
@admin_required
def get_next_admission_number():
    """Get the next available admission number for a class"""
    class_id = request.args.get('class_id')
    if not class_id:
        return jsonify({'error': 'Class ID is required'}), 400
        
    try:
        admission_number = generate_admission_number(class_id)
        return jsonify({'admission_number': admission_number}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
