from datetime import datetime
from bson import ObjectId
from app import mongo, bcrypt


class User:
    """User model for admin and student accounts"""
    
    @staticmethod
    def create_user(user_data):
        """Create a new user in the database"""
        user_data['created_at'] = datetime.utcnow()
        user_data['updated_at'] = datetime.utcnow()
        user_data['is_active'] = True
        
        # Hash password if provided
        if 'password' in user_data and user_data['password']:
            user_data['password'] = bcrypt.generate_password_hash(user_data['password']).decode('utf-8')
        
        result = mongo.db.users.insert_one(user_data)
        user_data['_id'] = result.inserted_id
        return user_data
    
    @staticmethod
    def find_by_id(user_id):
        """Find user by ID"""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
        return mongo.db.users.find_one({'_id': user_id, 'is_active': True})
    
    @staticmethod
    def find_by_username(username):
        """Find user by username"""
        return mongo.db.users.find_one({'username': username, 'is_active': True})
    
    @staticmethod
    def find_by_admission_number(admission_number):
        """Find student by admission number"""
        return mongo.db.users.find_one({
            'admission_number': admission_number,
            'user_type': 'student',
            'is_active': True
        })
    
    @staticmethod
    def find_by_admission_number_ci(admission_number):
        """Find student by admission number, case-insensitive"""
        import re
        pattern = re.compile(f'^{re.escape(admission_number)}$', re.IGNORECASE)
        return mongo.db.users.find_one({
            'admission_number': pattern,
            'user_type': 'student',
            'is_active': True
        })
    
    @staticmethod
    def verify_password(user, password):
        """Verify user password"""
        if not user or not user.get('password'):
            return False
        return bcrypt.check_password_hash(user['password'], password)
    
    @staticmethod
    def verify_student_admission_surname_login(admission_number: str, password: str):
        """
        Verify student login using admission number + any part of their name.
        Password can be any single word from their full name, first name, or last name.
        """
        # Find student by admission number (case-insensitive)
        student = User.find_by_admission_number_ci(admission_number)
        if not student:
            return None
        
        # Get all name tokens
        def get_all_tokens(s: str):
            if not s:
                return set()
            return set(s.lower().split())
        
        name_tokens = get_all_tokens(student.get('full_name', ''))
        name_tokens.update(get_all_tokens(student.get('first_name', '')))
        name_tokens.update(get_all_tokens(student.get('last_name', '')))
        
        # Check if password matches any name token
        password_lower = password.lower().strip()
        if password_lower in name_tokens:
            return student
        
        # Fallback: check hashed password
        if User.verify_password(student, password):
            return student
        
        return None
    
    @staticmethod
    def update_user(user_id, update_data):
        """Update user data"""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
        
        update_data['updated_at'] = datetime.utcnow()
        
        # Hash password if being updated
        if 'password' in update_data and update_data['password']:
            update_data['password'] = bcrypt.generate_password_hash(update_data['password']).decode('utf-8')
        
        result = mongo.db.users.update_one(
            {'_id': user_id},
            {'$set': update_data}
        )
        return result.modified_count > 0
    
    @staticmethod
    def delete_user_permanently(user_id):
        """Permanently delete user from database"""
        if isinstance(user_id, str):
            user_id = ObjectId(user_id)
        result = mongo.db.users.delete_one({'_id': user_id})
        return result.deleted_count > 0
    
    @staticmethod
    def get_users_by_type(user_type, limit=50, skip=0):
        """Get users by type with pagination"""
        return list(mongo.db.users.find({
            'user_type': user_type,
            'is_active': True
        }).skip(skip).limit(limit).sort('created_at', -1))
    
    @staticmethod
    def count_users_by_type(user_type):
        """Count users by type"""
        return mongo.db.users.count_documents({
            'user_type': user_type,
            'is_active': True
        })
    
    @staticmethod
    def get_students_by_class(class_name):
        """Get all students in a specific class"""
        return list(mongo.db.users.find({
            'user_type': 'student',
            'class_id': class_name,
            'is_active': True
        }).sort('full_name', 1))
