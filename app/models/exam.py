from datetime import datetime
from bson import ObjectId
from app import mongo


class Exam:
    """Exam model for managing examinations"""
    
    @staticmethod
    def create_exam(exam_data):
        """Create a new exam"""
        exam_data['created_at'] = datetime.utcnow()
        exam_data['updated_at'] = datetime.utcnow()
        exam_data['is_active'] = True
        exam_data['status'] = exam_data.get('status', 'draft')
        
        result = mongo.db.exams.insert_one(exam_data)
        exam_data['_id'] = result.inserted_id
        return exam_data
    
    @staticmethod
    def find_by_id(exam_id):
        """Find exam by ID"""
        if isinstance(exam_id, str):
            exam_id = ObjectId(exam_id)
        return mongo.db.exams.find_one({'_id': exam_id, 'is_active': True})
    
    @staticmethod
    def get_active_exams_for_student(student_class, student_arms=None, student_id=None):
        """
        Get active exams available for a student's class.
        Exams are automatically available based on their start_time and end_time,
        or if manually_enabled is True.
        
        Matching logic:
        - Exact match: student 'JSS 1 A' matches exam with 'JSS 1 A'
        - Base class match: student 'JSS 1' matches exam with 'JSS 1', 'JSS 1 A', 'JSS 1 B', etc.
        """
        import re
        now = datetime.utcnow()
        
        # Create regex pattern to match student's class:
        # - Exact match OR
        # - Student class followed by space and arm letter
        escaped_class = re.escape(student_class)
        class_pattern = f'^{escaped_class}( [A-Z])?$'
        
        # Build the base query for eligible classes
        base_query = {
            'is_active': True,
            'eligible_classes': {'$elemMatch': {'$regex': class_pattern, '$options': 'i'}}
        }
        
        # Time-based OR manual activation
        availability_conditions = [
            # Manually enabled
            {'manually_enabled': True, 'status': 'active'},
            # Time-based: current time is between start and end
            {
                'start_time': {'$lte': now},
                'end_time': {'$gte': now}
            }
        ]
        
        base_query['$or'] = availability_conditions
        
        # Debug query
        print(f"[DEBUG] Exam query: {base_query}")
        
        exams = list(mongo.db.exams.find(base_query).sort('created_at', -1))
        
        # Debug: log count
        print(f"[DEBUG] Raw query returned {len(exams)} exams")
        
        # Filter out exams the student has already completed
        if student_id:
            if isinstance(student_id, str):
                student_id = ObjectId(student_id)
            
            # Get completed exam IDs for this student
            completed_results = mongo.db.exam_results.find({
                'student_id': student_id,
                'status': {'$in': ['completed', 'mcq_completed']}
            }, {'exam_id': 1})
            
            completed_exam_ids = {r['exam_id'] for r in completed_results}
            
            # Filter out completed exams
            exams = [e for e in exams if e['_id'] not in completed_exam_ids]
        
        return exams
    
    @staticmethod
    def get_exams_by_subject(subject_id):
        """Get exams by subject"""
        return list(mongo.db.exams.find({
            'subject_id': subject_id if isinstance(subject_id, ObjectId) else ObjectId(subject_id),
            'is_active': True
        }).sort('created_at', -1))
    
    @staticmethod
    def update_exam(exam_id, update_data):
        """Update exam data"""
        if isinstance(exam_id, str):
            exam_id = ObjectId(exam_id)
        
        update_data['updated_at'] = datetime.utcnow()
        
        result = mongo.db.exams.update_one(
            {'_id': exam_id},
            {'$set': update_data}
        )
        return result.modified_count > 0
    
    @staticmethod
    def get_all_exams(limit=50, skip=0, filters=None):
        """Get all exams with pagination and optional filters"""
        query = {'is_active': True}
        
        if filters:
            if filters.get('subject'):
                query['subject'] = filters['subject']
            if filters.get('academic_term'):
                query['academic_term'] = filters['academic_term']
            if filters.get('academic_session'):
                query['academic_session'] = filters['academic_session']
        
        total = mongo.db.exams.count_documents(query)
        exams = list(mongo.db.exams.find(query).skip(skip).limit(limit).sort('created_at', -1))
        
        return exams, total
    
    @staticmethod
    def get_mcq_scores_for_export(exam_id):
        """Return a list of student MCQ score rows for export"""
        if isinstance(exam_id, str):
            exam_id = ObjectId(exam_id)
        
        results = list(mongo.db.exam_results.find({
            'exam_id': exam_id,
            'status': {'$in': ['completed', 'mcq_completed']}
        }))
        
        export_rows = []
        for result in results:
            student = mongo.db.users.find_one({'_id': result['student_id']})
            if student:
                mcq_score = result.get('mcq_score', {})
                export_rows.append({
                    'admission_number': student.get('admission_number', ''),
                    'full_name': student.get('full_name', ''),
                    'class': student.get('class_id', ''),
                    'correct_answers': mcq_score.get('correct_answers', 0),
                    'total_questions': mcq_score.get('total_questions', 0),
                    'calculated_marks': mcq_score.get('calculated_marks', 0),
                    'max_marks': mcq_score.get('max_marks', 30)
                })
        
        return export_rows


class Question:
    """Question model for exam questions"""
    
    @staticmethod
    def create_question(question_data):
        """Create a new question"""
        question_data['created_at'] = datetime.utcnow()
        question_data['updated_at'] = datetime.utcnow()
        question_data['is_active'] = True
        
        result = mongo.db.questions.insert_one(question_data)
        question_data['_id'] = result.inserted_id
        return question_data
    
    @staticmethod
    def find_by_id(question_id):
        """Find question by ID"""
        if isinstance(question_id, str):
            question_id = ObjectId(question_id)
        return mongo.db.questions.find_one({'_id': question_id, 'is_active': True})
    
    @staticmethod
    def get_questions_by_exam(exam_id):
        """Get all questions for an exam"""
        if isinstance(exam_id, str):
            exam_id = ObjectId(exam_id)
        
        questions = list(mongo.db.questions.find({
            'exam_id': exam_id,
            'is_active': True
        }).sort('question_number', 1))
        
        return questions
    
    @staticmethod
    def get_mcq_questions_by_exam(exam_id):
        """Get MCQ questions for an exam"""
        if isinstance(exam_id, str):
            exam_id = ObjectId(exam_id)
        
        return list(mongo.db.questions.find({
            'exam_id': exam_id,
            'question_type': 'mcq',
            'is_active': True
        }).sort('question_number', 1))
    
    @staticmethod
    def get_theory_questions_by_exam(exam_id):
        """Get theory questions for an exam"""
        if isinstance(exam_id, str):
            exam_id = ObjectId(exam_id)
        
        return list(mongo.db.questions.find({
            'exam_id': exam_id,
            'question_type': 'theory',
            'is_active': True
        }).sort('question_number', 1))
    
    @staticmethod
    def update_question(question_id, update_data):
        """Update a question"""
        if isinstance(question_id, str):
            question_id = ObjectId(question_id)
        
        update_data['updated_at'] = datetime.utcnow()
        
        result = mongo.db.questions.update_one(
            {'_id': question_id},
            {'$set': update_data}
        )
        return result.modified_count > 0
    
    @staticmethod
    def delete_question(question_id):
        """Soft delete a question"""
        if isinstance(question_id, str):
            question_id = ObjectId(question_id)
        
        result = mongo.db.questions.update_one(
            {'_id': question_id},
            {'$set': {'is_active': False, 'updated_at': datetime.utcnow()}}
        )
        return result.modified_count > 0


class ExamSession:
    """Exam session model for tracking student exam attempts"""
    
    @staticmethod
    def create_session(session_data):
        """Create a new exam session"""
        session_data['created_at'] = datetime.utcnow()
        session_data['start_time'] = datetime.utcnow()
        session_data['status'] = 'in_progress'
        session_data['answers'] = {}
        
        result = mongo.db.exam_sessions.insert_one(session_data)
        session_data['_id'] = result.inserted_id
        return session_data
    
    @staticmethod
    def find_by_id(session_id):
        """Find exam session by ID"""
        if isinstance(session_id, str):
            session_id = ObjectId(session_id)
        return mongo.db.exam_sessions.find_one({'_id': session_id})
    
    @staticmethod
    def find_active_session(student_id, exam_id):
        """Find an active exam session for a student"""
        if isinstance(student_id, str):
            student_id = ObjectId(student_id)
        if isinstance(exam_id, str):
            exam_id = ObjectId(exam_id)
        
        return mongo.db.exam_sessions.find_one({
            'student_id': student_id,
            'exam_id': exam_id,
            'status': 'in_progress'
        })
    
    @staticmethod
    def submit_mcq_answer(session_id, question_id, selected_option):
        """Persist a student's MCQ answer"""
        if isinstance(session_id, str):
            session_id = ObjectId(session_id)
        if isinstance(question_id, str):
            question_id = ObjectId(question_id)
        
        # Get the question to check correct answer
        question = Question.find_by_id(question_id)
        is_correct = False
        if question and question.get('correct_option') is not None:
            is_correct = question['correct_option'] == selected_option
        
        # Update the session with the answer
        answer_key = f"answers.{str(question_id)}"
        
        result = mongo.db.exam_sessions.update_one(
            {'_id': session_id},
            {
                '$set': {
                    answer_key: {
                        'selected_option': selected_option,
                        'is_correct': is_correct,
                        'answered_at': datetime.utcnow()
                    }
                }
            }
        )
        
        return result.modified_count > 0, is_correct
    
    @staticmethod
    def complete_session(session_id, update_data=None):
        """Mark an exam session as completed"""
        if isinstance(session_id, str):
            session_id = ObjectId(session_id)
        
        update = {
            'status': 'completed',
            'end_time': datetime.utcnow()
        }
        
        if update_data:
            update.update(update_data)
        
        result = mongo.db.exam_sessions.update_one(
            {'_id': session_id},
            {'$set': update}
        )
        return result.modified_count > 0


class ExamResult:
    """Exam result model for storing student exam results"""
    
    @staticmethod
    def create_result(result_data):
        """Create a new exam result"""
        result_data['created_at'] = datetime.utcnow()
        result_data['updated_at'] = datetime.utcnow()
        
        result = mongo.db.exam_results.insert_one(result_data)
        result_data['_id'] = result.inserted_id
        return result_data
    
    @staticmethod
    def find_by_session(session_id):
        """Find exam result by session ID"""
        if isinstance(session_id, str):
            session_id = ObjectId(session_id)
        return mongo.db.exam_results.find_one({'session_id': session_id})
    
    @staticmethod
    def find_by_id(result_id):
        """Find exam result by result ID"""
        if isinstance(result_id, str):
            result_id = ObjectId(result_id)
        return mongo.db.exam_results.find_one({'_id': result_id})
    
    @staticmethod
    def calculate_mcq_score(session_doc, max_mcq_marks=30):
        """Calculate MCQ score for a completed session
        
        Score formula: (correct_answers / total_mcq_questions) * max_mcq_marks
        NOT: correct_answers / answered_questions
        """
        from bson import ObjectId
        
        answers = session_doc.get('answers', {})
        exam_id = session_doc.get('exam_id')
        
        # Get actual total MCQ questions for this exam
        total_mcq_questions = mongo.db.questions.count_documents({
            'exam_id': ObjectId(exam_id) if isinstance(exam_id, str) else exam_id,
            'question_type': 'mcq',
            'is_active': True
        })
        
        # If randomization was used, use the number of selected questions
        selected_question_ids = session_doc.get('selected_question_ids')
        if selected_question_ids:
            total_mcq_questions = len(selected_question_ids)
        
        # Count correct answers
        correct_count = 0
        for question_id, answer_data in answers.items():
            if answer_data.get('is_correct', False):
                correct_count += 1
        
        # Calculate marks: (correct / total_questions) * max_marks
        if total_mcq_questions > 0:
            calculated_marks = round((correct_count / total_mcq_questions) * max_mcq_marks, 2)
        else:
            calculated_marks = 0
        
        return {
            'correct_answers': correct_count,
            'total_questions': total_mcq_questions,
            'calculated_marks': calculated_marks,
            'max_marks': max_mcq_marks
        }
    
    @staticmethod
    def get_results_by_exam_and_class(exam_id, class_filter=None):
        """Get exam results filtered by exam and optionally by class"""
        if isinstance(exam_id, str):
            exam_id = ObjectId(exam_id)
        
        query = {
            'exam_id': exam_id,
            'status': {'$in': ['completed', 'mcq_completed']}
        }
        
        results = list(mongo.db.exam_results.find(query))
        
        # Enrich with student data and filter by class if needed
        enriched_results = []
        for result in results:
            student = mongo.db.users.find_one({'_id': result['student_id']})
            if student:
                if class_filter and student.get('class_id') != class_filter:
                    continue
                
                result['student'] = {
                    'admission_number': student.get('admission_number', ''),
                    'full_name': student.get('full_name', ''),
                    'class_id': student.get('class_id', '')
                }
                enriched_results.append(result)
        
        return enriched_results
    
    @staticmethod
    def update_result(result_id, update_data):
        """Update exam result"""
        if isinstance(result_id, str):
            result_id = ObjectId(result_id)
        
        update_data['updated_at'] = datetime.utcnow()
        
        result = mongo.db.exam_results.update_one(
            {'_id': result_id},
            {'$set': update_data}
        )
        return result.modified_count > 0
    
    @staticmethod
    def update_theory_and_ca_scores(result_id, theory_score=None, ca_score=None):
        """Update theory and CA scores for a result"""
        if isinstance(result_id, str):
            result_id = ObjectId(result_id)
        
        update_data = {'updated_at': datetime.utcnow()}
        
        if theory_score is not None:
            update_data['theory_score'] = theory_score
        if ca_score is not None:
            update_data['ca_score'] = ca_score
        
        result = mongo.db.exam_results.update_one(
            {'_id': result_id},
            {'$set': update_data}
        )
        return result.modified_count > 0
