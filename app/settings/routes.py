from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from app import mongo
from bson import ObjectId

from app.settings import bp

from datetime import datetime

@bp.route('/academic', methods=['GET'])
@jwt_required()
def get_academic_settings():
    """Get current academic session and term settings"""
    settings = mongo.db.system_settings.find_one({'type': 'academic'})
    
    # Dynamic session generation (Current Year - 5 to Current Year + 15)
    # This automatically updates as the years progress "to infinity"
    current_year = datetime.now().year
    dynamic_sessions = []
    for i in range(-5, 16):
        start_year = current_year + i
        dynamic_sessions.append(f"{start_year}/{start_year + 1}")
    
    if not settings:
        # Default settings if none exist
        default_settings = {
            'type': 'academic',
            'current_session': f'{current_year}/{current_year + 1}',
            'current_term': '1st Term',
            'available_sessions': dynamic_sessions,
            'available_terms': ['1st Term', '2nd Term', '3rd Term']
        }
        mongo.db.system_settings.insert_one(default_settings)
        settings = default_settings
    
    # Ensure returned available_sessions is always dynamic/up-to-date
    # merging with any manually added ones if they exist in DB (optional, but safer to just use dynamic for consistency)
    return jsonify({
        'current_session': settings.get('current_session'),
        'current_term': settings.get('current_term'),
        'available_sessions': dynamic_sessions,  # Always return dynamic list
        'available_terms': settings.get('available_terms', ['1st Term', '2nd Term', '3rd Term'])
    }), 200

@bp.route('/academic', methods=['POST'])
@jwt_required()
def update_academic_settings():
    """Update current academic session and term"""
    claims = get_jwt()
    if claims.get('user_type') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
        
    data = request.get_json()
    
    update_data = {}
    if 'current_session' in data:
        update_data['current_session'] = data['current_session']
    if 'current_term' in data:
        update_data['current_term'] = data['current_term']
        
    if not update_data:
        return jsonify({'message': 'No changes provided'}), 200
        
    mongo.db.system_settings.update_one(
        {'type': 'academic'},
        {'$set': update_data},
        upsert=True
    )
    
    return jsonify({'message': 'Academic settings updated successfully', 'settings': update_data}), 200
