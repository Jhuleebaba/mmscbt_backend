from datetime import datetime
from bson import ObjectId
from app import mongo


class Class:
    """Class model for managing school classes"""
    
    @staticmethod
    def create_class(class_data):
        """Create a new class"""
        class_data['created_at'] = datetime.utcnow()
        class_data['updated_at'] = datetime.utcnow()
        class_data['is_active'] = True
        
        result = mongo.db.classes.insert_one(class_data)
        class_data['_id'] = result.inserted_id
        return class_data
    
    @staticmethod
    def find_by_id(class_id):
        """Find class by ID"""
        try:
            if isinstance(class_id, str):
                class_id = ObjectId(class_id)
            return mongo.db.classes.find_one({'_id': class_id, 'is_active': True})
        except:
            return None
    
    @staticmethod
    def find_by_name(class_name):
        """Find class by name"""
        return (mongo.db.classes.find_one({'name': class_name, 'is_active': True}) or 
                mongo.db.classes.find_one({'class_name': class_name, 'is_active': True}))
    
    @staticmethod
    def get_all_classes():
        """Get all active classes ordered by level"""
        try:
            if mongo is None or mongo.db is None:
                return []
            
            classes = list(mongo.db.classes.find({
                'is_active': True
            }).sort([('level', 1), ('name', 1)]))
            
            # Normalize field names
            normalized_classes = []
            for cls in classes:
                normalized_cls = dict(cls)
                
                # Ensure 'name' field exists
                if 'name' not in normalized_cls and 'class_name' in normalized_cls:
                    normalized_cls['name'] = normalized_cls['class_name']
                
                # Ensure 'arms' field exists
                if 'arms' not in normalized_cls:
                    normalized_cls['arms'] = []
                
                normalized_classes.append(normalized_cls)
            
            return normalized_classes
        except Exception as e:
            print(f"Error in get_all_classes: {str(e)}")
            return []
    
    @staticmethod
    def update_class(class_id, update_data):
        """Update class data"""
        if isinstance(class_id, str):
            class_id = ObjectId(class_id)
        
        update_data['updated_at'] = datetime.utcnow()
        
        result = mongo.db.classes.update_one(
            {'_id': class_id},
            {'$set': update_data}
        )
        return result.modified_count > 0
    
    @staticmethod
    def deactivate_class(class_id):
        """Soft delete class"""
        if isinstance(class_id, str):
            class_id = ObjectId(class_id)
        
        result = mongo.db.classes.update_one(
            {'_id': class_id},
            {'$set': {'is_active': False, 'updated_at': datetime.utcnow()}}
        )
        return result.modified_count > 0


class Subject:
    """Subject model for managing exam subjects"""
    
    @staticmethod
    def create_subject(subject_data):
        """Create a new subject"""
        subject_data['created_at'] = datetime.utcnow()
        subject_data['updated_at'] = datetime.utcnow()
        subject_data['is_active'] = True
        
        # Ensure both 'name' and 'subject_name' fields are set
        if 'name' in subject_data and 'subject_name' not in subject_data:
            subject_data['subject_name'] = subject_data['name']
        if 'code' in subject_data and 'subject_code' not in subject_data:
            subject_data['subject_code'] = subject_data['code']
        
        result = mongo.db.subjects.insert_one(subject_data)
        subject_data['_id'] = result.inserted_id
        return subject_data
    
    @staticmethod
    def find_by_id(subject_id):
        """Find subject by ID"""
        try:
            if isinstance(subject_id, str):
                subject_id = ObjectId(subject_id)
            return mongo.db.subjects.find_one({'_id': subject_id, 'is_active': True})
        except:
            return None
    
    @staticmethod
    def find_by_name(subject_name):
        """Find subject by name"""
        return (mongo.db.subjects.find_one({'name': subject_name, 'is_active': True}) or 
                mongo.db.subjects.find_one({'subject_name': subject_name, 'is_active': True}))
    
    @staticmethod
    def get_all_subjects():
        """Get all active subjects"""
        try:
            if mongo is None or mongo.db is None:
                return []
            
            subjects = list(mongo.db.subjects.find({
                'is_active': True
            }).sort([('name', 1), ('subject_name', 1)]))
            
            # Normalize field names
            normalized_subjects = []
            for subj in subjects:
                normalized_subj = dict(subj)
                
                if 'name' not in normalized_subj and 'subject_name' in normalized_subj:
                    normalized_subj['name'] = normalized_subj['subject_name']
                if 'code' not in normalized_subj and 'subject_code' in normalized_subj:
                    normalized_subj['code'] = normalized_subj['subject_code']
                if 'applicable_classes' not in normalized_subj:
                    normalized_subj['applicable_classes'] = []
                
                normalized_subjects.append(normalized_subj)
            
            return normalized_subjects
        except Exception as e:
            print(f"Error in get_all_subjects: {str(e)}")
            return []
    
    @staticmethod
    def get_subjects_by_class(class_name):
        """Get subjects applicable to a specific class (supports both old and new format)"""
        # Support both old format (list of class names) and new format (list of objects with class and arms)
        subjects = list(mongo.db.subjects.find({
            '$or': [
                # Old format: applicable_classes is array of strings
                {'applicable_classes': {'$in': [class_name]}},
                # New format: applicable_classes is array of objects with 'class' field
                {'applicable_classes.class': class_name}
            ],
            'is_active': True
        }).sort('name', 1))
        return subjects
    
    @staticmethod
    def get_subjects_by_class_arm(class_name, arm):
        """Get subjects applicable to a specific class AND arm combination"""
        subjects = list(mongo.db.subjects.find({
            '$or': [
                # Old format: applicable_classes contains just the class name (applies to all arms)
                {'applicable_classes': {'$in': [class_name]}, 'applicable_classes': {'$not': {'$elemMatch': {'class': {'$exists': True}}}}},
                # New format: applicable_classes has objects with matching class and arm
                {
                    'applicable_classes': {
                        '$elemMatch': {
                            'class': class_name,
                            '$or': [
                                {'arms': {'$in': [arm]}},
                                {'arms': {'$size': 0}},  # Empty arms means all arms
                                {'arms': {'$exists': False}}  # No arms field means all arms
                            ]
                        }
                    }
                }
            ],
            'is_active': True
        }).sort('name', 1))
        return subjects
    
    @staticmethod
    def update_subject(subject_id, update_data):
        """Update subject data"""
        if isinstance(subject_id, str):
            subject_id = ObjectId(subject_id)
        
        update_data['updated_at'] = datetime.utcnow()
        
        if 'name' in update_data and 'subject_name' not in update_data:
            update_data['subject_name'] = update_data['name']
        if 'code' in update_data and 'subject_code' not in update_data:
            update_data['subject_code'] = update_data['code']
        
        result = mongo.db.subjects.update_one(
            {'_id': subject_id},
            {'$set': update_data}
        )
        return result.modified_count > 0
    
    @staticmethod
    def deactivate_subject(subject_id):
        """Soft delete subject"""
        if isinstance(subject_id, str):
            subject_id = ObjectId(subject_id)
        
        result = mongo.db.subjects.update_one(
            {'_id': subject_id},
            {'$set': {'is_active': False, 'updated_at': datetime.utcnow()}}
        )
        return result.modified_count > 0


class AcademicSettings:
    """Model for managing academic sessions and terms"""
    
    TERM_NAMES = {
        1: "First Term",
        2: "Second Term", 
        3: "Third Term"
    }
    
    @staticmethod
    def get_current_settings():
        """Get current active academic settings"""
        settings = mongo.db.academic_settings.find_one(
            {"is_active": True},
            sort=[("created_at", -1)]
        )
        
        if settings:
            settings['id'] = str(settings.pop('_id'))
        
        return settings
    
    @staticmethod
    def get_all_sessions():
        """Get list of all academic sessions"""
        sessions = mongo.db.academic_settings.distinct('current_session')
        return sorted(sessions, reverse=True) if sessions else []
    
    @staticmethod
    def set_academic_period(session, term, term_dates=None):
        """
        Set academic period (session and term)
        
        Args:
            session: Academic session (e.g., "2024/2025")
            term: Current term (1, 2, or 3)
            term_dates: Optional dict with term date configurations
        """
        if term not in [1, 2, 3]:
            raise ValueError("Term must be 1, 2, or 3")
        
        # Validate term dates if provided
        if term_dates:
            for term_num in [1, 2, 3]:
                term_key = f"term_{term_num}"
                if term_key in term_dates:
                    start_date = term_dates[term_key].get('start_date')
                    end_date = term_dates[term_key].get('end_date')
                    if start_date and end_date:
                        start = datetime.strptime(start_date, '%Y-%m-%d')
                        end = datetime.strptime(end_date, '%Y-%m-%d')
                        if start >= end:
                            raise ValueError(f"Invalid date range for {term_key}")
        
        # Check if settings exist for this session
        existing = mongo.db.academic_settings.find_one({'current_session': session})
        
        if existing:
            # Update existing
            update_data = {
                'current_term': term,
                'is_active': True,
                'updated_at': datetime.utcnow()
            }
            if term_dates:
                update_data['term_dates'] = term_dates
            
            # Deactivate other settings
            mongo.db.academic_settings.update_many(
                {'_id': {'$ne': existing['_id']}},
                {'$set': {'is_active': False}}
            )
            
            mongo.db.academic_settings.update_one(
                {'_id': existing['_id']},
                {'$set': update_data}
            )
            return str(existing['_id'])
        else:
            # Create new
            mongo.db.academic_settings.update_many(
                {'is_active': True},
                {'$set': {'is_active': False}}
            )
            
            new_settings = {
                'current_session': session,
                'current_term': term,
                'term_dates': term_dates or {},
                'is_active': True,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            
            result = mongo.db.academic_settings.insert_one(new_settings)
            return str(result.inserted_id)
    
    @staticmethod
    def update_current_term(new_term):
        """Update current term only"""
        if new_term not in [1, 2, 3]:
            raise ValueError("Term must be 1, 2, or 3")
        
        result = mongo.db.academic_settings.update_one(
            {'is_active': True},
            {'$set': {'current_term': new_term, 'updated_at': datetime.utcnow()}}
        )
        
        if result.matched_count == 0:
            raise ValueError("No active academic settings found")
        
        return AcademicSettings.get_current_settings()
    
    @staticmethod
    def set_term_dates(session, term_number, start_date, end_date):
        """Set dates for a specific term"""
        if term_number not in [1, 2, 3]:
            raise ValueError("Term number must be 1, 2, or 3")
        
        term_key = f"term_{term_number}"
        
        result = mongo.db.academic_settings.update_one(
            {'current_session': session, 'is_active': True},
            {
                '$set': {
                    f'term_dates.{term_key}.start_date': start_date,
                    f'term_dates.{term_key}.end_date': end_date,
                    'updated_at': datetime.utcnow()
                }
            }
        )
        
        return result.modified_count > 0
    
    @staticmethod
    def get_term_name(term_number):
        """Get display name for term number"""
        return AcademicSettings.TERM_NAMES.get(term_number, f"Term {term_number}")
    
    @staticmethod
    def get_terms_list():
        """Get list of terms for dropdown"""
        return [
            {'value': 1, 'label': 'First Term'},
            {'value': 2, 'label': 'Second Term'},
            {'value': 3, 'label': 'Third Term'}
        ]

