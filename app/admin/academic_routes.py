from flask import request, jsonify
from bson import ObjectId
from app.admin import bp
from app import mongo
from app.models.academic import Class, Subject
from app.utils.decorators import admin_required
from app.utils.validators import validate_required_fields, sanitize_string
from datetime import datetime


@bp.route('/classes', methods=['GET'])
@admin_required
def get_classes():
    """Get all classes"""
    try:
        classes = Class.get_all_classes()
        
        serialized_classes = []
        for cls in classes:
            serialized_classes.append({
                'id': str(cls['_id']),
                'name': cls.get('name', cls.get('class_name', '')),
                'level': cls.get('level', 0),
                'description': cls.get('description', ''),
                'arms': cls.get('arms', []),
                'is_active': cls.get('is_active', True)
            })
        
        return jsonify({
            'message': 'Classes retrieved successfully',
            'classes': serialized_classes
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/classes', methods=['POST'])
@admin_required
def create_class():
    """Create a new class"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    required_fields = ['name']
    is_valid, missing = validate_required_fields(data, required_fields)
    
    if not is_valid:
        return jsonify({'error': f'Missing required fields: {", ".join(missing)}'}), 400
    
    # Check if class already exists
    existing = Class.find_by_name(data['name'])
    if existing:
        return jsonify({'error': 'Class already exists'}), 400
    
    class_data = {
        'name': sanitize_string(data['name']),
        'class_name': sanitize_string(data['name']),
        'level': data.get('level', 1),
        'description': data.get('description', ''),
        'arms': data.get('arms', ['A'])
    }
    
    new_class = Class.create_class(class_data)
    
    return jsonify({
        'message': 'Class created successfully',
        'class': {
            'id': str(new_class['_id']),
            'name': new_class['name'],
            'level': new_class.get('level', 1),
            'arms': new_class.get('arms', [])
        }
    }), 201


@bp.route('/classes/<class_id>/arms', methods=['PUT'])
@admin_required
def update_class_arms(class_id):
    """Update arms for a class"""
    data = request.get_json()
    
    if not data or 'arms' not in data:
        return jsonify({'error': 'Arms data is required'}), 400
    
    arms = data['arms']
    if not isinstance(arms, list):
        return jsonify({'error': 'Arms must be a list'}), 400
    
    success = Class.update_class(class_id, {'arms': arms})
    
    if not success:
        return jsonify({'error': 'Failed to update class arms'}), 500
    
    updated_class = Class.find_by_id(class_id)
    
    return jsonify({
        'message': 'Class arms updated successfully',
        'class': {
            'id': str(updated_class['_id']),
            'name': updated_class.get('name', ''),
            'arms': updated_class.get('arms', [])
        }
    }), 200


@bp.route('/expanded-classes', methods=['GET'])
@admin_required
def get_expanded_classes():
    """Get classes with arms expanded as separate entries"""
    try:
        classes = Class.get_all_classes()
        
        expanded = []
        for cls in classes:
            class_name = cls.get('name', cls.get('class_name', ''))
            arms = cls.get('arms', ['A'])
            
            if not arms:
                arms = ['A']
            
            for arm in arms:
                display_name = f"{class_name} {arm}" if arm else class_name
                expanded.append({
                    'id': f"{str(cls['_id'])}_{arm}",
                    'name': display_name,
                    'display_name': display_name,
                    'level': cls.get('level', 0),
                    'description': cls.get('description', ''),
                    'base_class': class_name,
                    'arm': arm,
                    'is_active': cls.get('is_active', True)
                })
        
        return jsonify({
            'message': 'Expanded classes retrieved successfully',
            'expanded_classes': expanded
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ==================== SUBJECTS ====================

@bp.route('/subjects', methods=['GET'])
@admin_required
def get_subjects():
    """Get all subjects"""
    try:
        subjects = Subject.get_all_subjects()
        
        serialized_subjects = []
        for subj in subjects:
            serialized_subjects.append({
                'id': str(subj['_id']),
                'name': subj.get('name', subj.get('subject_name', '')),
                'code': subj.get('code', subj.get('subject_code', '')),
                'description': subj.get('description', ''),
                'applicable_classes': subj.get('applicable_classes', []),
                'is_core': subj.get('is_core', False),
                'is_active': subj.get('is_active', True)
            })
        
        return jsonify({
            'message': 'Subjects retrieved successfully',
            'subjects': serialized_subjects
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/subjects', methods=['POST'])
@admin_required
def create_subject():
    """Create a new subject"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    required_fields = ['name']
    is_valid, missing = validate_required_fields(data, required_fields)
    
    if not is_valid:
        return jsonify({'error': f'Missing required fields: {", ".join(missing)}'}), 400
    
    # Check if subject already exists
    existing = Subject.find_by_name(data['name'])
    if existing:
        return jsonify({'error': 'Subject already exists'}), 400
    
    # Generate code if not provided
    code = data.get('code', '')
    if not code:
        # Generate code from name (first 3 letters uppercase)
        code = ''.join(c for c in data['name'] if c.isalpha())[:3].upper()
    
    subject_data = {
        'name': sanitize_string(data['name']),
        'subject_name': sanitize_string(data['name']),
        'code': code,
        'subject_code': code,
        'description': data.get('description', ''),
        'applicable_classes': data.get('applicable_classes', []),
        'is_core': data.get('is_core', False)
    }
    
    new_subject = Subject.create_subject(subject_data)
    
    return jsonify({
        'message': 'Subject created successfully',
        'subject': {
            'id': str(new_subject['_id']),
            'name': new_subject['name'],
            'code': new_subject['code'],
            'applicable_classes': new_subject.get('applicable_classes', [])
        }
    }), 201


@bp.route('/subjects/<subject_id>', methods=['PUT'])
@admin_required
def update_subject(subject_id):
    """Update an existing subject"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    # Find subject
    subject = Subject.find_by_id(subject_id)
    if not subject:
        return jsonify({'error': 'Subject not found'}), 404
    
    # Build update data
    update_data = {}
    allowed_fields = ['name', 'code', 'description', 'applicable_classes', 'is_core']
    
    for field in allowed_fields:
        if field in data:
            update_data[field] = data[field]
    
    success = Subject.update_subject(subject_id, update_data)
    
    if not success:
        return jsonify({'error': 'Failed to update subject'}), 500
    
    updated_subject = Subject.find_by_id(subject_id)
    
    return jsonify({
        'message': 'Subject updated successfully',
        'subject': {
            'id': str(updated_subject['_id']),
            'name': updated_subject.get('name', ''),
            'code': updated_subject.get('code', ''),
            'applicable_classes': updated_subject.get('applicable_classes', [])
        }
    }), 200


@bp.route('/subjects/<subject_id>', methods=['DELETE'])
@admin_required
def delete_subject(subject_id):
    """Soft delete a subject"""
    subject = Subject.find_by_id(subject_id)
    
    if not subject:
        return jsonify({'error': 'Subject not found'}), 404
    
    success = Subject.deactivate_subject(subject_id)
    
    if not success:
        return jsonify({'error': 'Failed to delete subject'}), 500
    
    return jsonify({'message': 'Subject deleted successfully'}), 200


# ==================== ACADEMIC SETTINGS ====================

from app.models.academic import AcademicSettings

@bp.route('/academic-settings', methods=['GET'])
@admin_required
def get_academic_settings():
    """Get current academic settings"""
    try:
        settings = AcademicSettings.get_current_settings()
        
        if not settings:
            return jsonify({
                'message': 'No academic settings configured',
                'settings': None
            }), 200
        
        return jsonify({'settings': settings}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/academic-settings', methods=['POST'])
@admin_required
def set_academic_settings():
    """Create or update academic settings"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        session = data.get('session')
        term = data.get('term')
        term_dates = data.get('term_dates')
        
        if not session:
            return jsonify({'error': 'Academic session is required'}), 400
        
        if not term:
            return jsonify({'error': 'Current term is required'}), 400
        
        settings_id = AcademicSettings.set_academic_period(
            session=session,
            term=int(term),
            term_dates=term_dates
        )
        
        return jsonify({
            'message': 'Academic settings saved successfully',
            'id': settings_id,
            'settings': AcademicSettings.get_current_settings()
        }), 200
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/academic-settings/term', methods=['PUT'])
@admin_required
def update_current_term():
    """Update current term only"""
    try:
        data = request.get_json()
        
        if not data or 'term' not in data:
            return jsonify({'error': 'Term is required'}), 400
        
        settings = AcademicSettings.update_current_term(int(data['term']))
        
        return jsonify({
            'message': 'Current term updated successfully',
            'settings': settings
        }), 200
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/academic-settings/term-dates', methods=['PUT'])
@admin_required
def set_term_dates():
    """Set dates for a specific term"""
    try:
        data = request.get_json()
        
        required_fields = ['session', 'term_number', 'start_date', 'end_date']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'{field} is required'}), 400
        
        success = AcademicSettings.set_term_dates(
            session=data['session'],
            term_number=int(data['term_number']),
            start_date=data['start_date'],
            end_date=data['end_date']
        )
        
        if success:
            return jsonify({
                'message': 'Term dates updated successfully',
                'settings': AcademicSettings.get_current_settings()
            }), 200
        else:
            return jsonify({'error': 'Failed to update term dates'}), 400
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/sessions', methods=['GET'])
@admin_required
def get_sessions():
    """Get list of all academic sessions"""
    try:
        sessions = AcademicSettings.get_all_sessions()
        return jsonify({'sessions': sessions}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/terms', methods=['GET'])
@admin_required
def get_terms():
    """Get list of terms for dropdown"""
    try:
        terms = AcademicSettings.get_terms_list()
        return jsonify({'terms': terms}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

