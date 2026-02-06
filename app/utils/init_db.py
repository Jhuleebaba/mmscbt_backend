from app import mongo, bcrypt
from app.models.user import User
import os


def initialize_database():
    """Initialize database with default admin user and preset classes"""
    
    # Create default admin if not exists
    admin = mongo.db.users.find_one({'username': 'admin', 'user_type': 'admin'})
    
    if not admin:
        default_password = os.environ.get('DEFAULT_ADMIN_PASSWORD', 'admin123')
        hashed_password = bcrypt.generate_password_hash(default_password).decode('utf-8')
        
        admin_data = {
            'username': 'admin',
            'password': hashed_password,
            'full_name': 'System Administrator',
            'user_type': 'admin',
            'is_active': True
        }
        
        mongo.db.users.insert_one(admin_data)
        print("[OK] Default admin user created (username: admin)")
    
    # Create default classes if not exists
    existing_classes = mongo.db.classes.count_documents({})
    
    if existing_classes == 0:
        default_classes = [
            {'name': 'JSS 1', 'level': 1, 'description': 'Junior Secondary School 1', 'arms': ['A']},
            {'name': 'JSS 2', 'level': 2, 'description': 'Junior Secondary School 2', 'arms': ['A']},
            {'name': 'JSS 3', 'level': 3, 'description': 'Junior Secondary School 3', 'arms': ['A']},
            {'name': 'SS 1', 'level': 4, 'description': 'Senior Secondary School 1', 'arms': ['A']},
            {'name': 'SS 2', 'level': 5, 'description': 'Senior Secondary School 2', 'arms': ['A']},
            {'name': 'SS 3', 'level': 6, 'description': 'Senior Secondary School 3', 'arms': ['A']},
        ]
        
        for class_data in default_classes:
            class_data['is_active'] = True
            mongo.db.classes.insert_one(class_data)
        
        print(f"[OK] Created {len(default_classes)} default classes")
    
    # Create indexes for better performance
    try:
        # Users collection indexes
        mongo.db.users.create_index('username', unique=True, sparse=True)
        mongo.db.users.create_index('admission_number', unique=True, sparse=True)
        mongo.db.users.create_index('user_type')
        
        # Exams collection indexes
        mongo.db.exams.create_index('is_active')
        mongo.db.exams.create_index('eligible_classes')
        mongo.db.exams.create_index([('start_time', 1), ('end_time', 1)])
        
        # Questions collection indexes
        mongo.db.questions.create_index('exam_id')
        mongo.db.questions.create_index([('exam_id', 1), ('question_type', 1)])
        
        # Exam sessions indexes
        mongo.db.exam_sessions.create_index([('student_id', 1), ('exam_id', 1)])
        mongo.db.exam_sessions.create_index('status')
        
        # Exam results indexes
        mongo.db.exam_results.create_index('exam_id')
        mongo.db.exam_results.create_index('student_id')
        mongo.db.exam_results.create_index('session_id')
        
        print("[OK] Database indexes created")
    except Exception as e:
        print(f"[WARN] Index creation warning (may already exist): {e}")
    
    print("[OK] Database initialization complete")

