from flask import request, jsonify
from bson import ObjectId
from datetime import datetime, timedelta
import secrets
from app.examinations import bp
from app import mongo
from app.models.exam import Exam, Question, ExamSession, ExamResult
from app.models.academic import Subject, Class
from app.utils.decorators import admin_required, exam_mode_required, get_current_user_data
from app.utils.validators import validate_required_fields, validate_question_data
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt

# ==================== ADMIN EXAM MANAGEMENT ====================

@bp.route('/exams', methods=['GET'])
@admin_required
def get_all_exams():
    """Get all exams (Admin)"""
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 50))
    skip = (page - 1) * limit
    
    filters = {}
    if request.args.get('subject'):
        filters['subject'] = request.args.get('subject')
    if request.args.get('academic_session'):
        filters['academic_session'] = request.args.get('academic_session')
    if request.args.get('academic_term'):
        filters['academic_term'] = request.args.get('academic_term')
    
    exams, total = Exam.get_all_exams(limit=limit, skip=skip, filters=filters)
    
    serialized_exams = []
    for exam in exams:
        # Get question count
        question_count = mongo.db.questions.count_documents({
            'exam_id': exam['_id'],
            'is_active': True
        })
        
        serialized_exams.append({
            'id': str(exam['_id']),
            'title': exam.get('title', ''),
            'subject': exam.get('subject', ''),
            'subject_id': str(exam['subject_id']) if exam.get('subject_id') else None,
            'description': exam.get('description', ''),
            'duration_minutes': exam.get('duration_minutes', 60),
            'max_mcq_marks': exam.get('max_mcq_marks', 30),
            'eligible_classes': exam.get('eligible_classes', []),
            'status': exam.get('status', 'draft'),
            'manually_enabled': exam.get('manually_enabled', False),
            'start_time': exam.get('start_time').isoformat() if exam.get('start_time') else None,
            'end_time': exam.get('end_time').isoformat() if exam.get('end_time') else None,
            'question_count': question_count,
            'academic_term': exam.get('academic_term', ''),
            'academic_session': exam.get('academic_session', ''),
            'enable_randomization': exam.get('enable_randomization', False),
            'mcq_count': exam.get('mcq_count', 0),
            'created_at': exam.get('created_at').isoformat() if exam.get('created_at') else None
        })
    
    return jsonify({
        'message': 'Exams retrieved successfully',
        'exams': serialized_exams,
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total,
            'pages': (total + limit - 1) // limit
        }
    }), 200


@bp.route('/exams', methods=['POST'])
@admin_required
def create_exam():
    """Create a new exam (Admin)"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    required_fields = ['title', 'subject']
    is_valid, missing = validate_required_fields(data, required_fields)
    
    if not is_valid:
        return jsonify({'error': f'Missing required fields: {", ".join(missing)}'}), 400
    
    # Parse dates if provided
    start_time = None
    end_time = None
    
    if data.get('start_time'):
        try:
            start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
        except Exception:
            start_time = datetime.utcnow()
    
    if data.get('end_time'):
        try:
            end_time = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
        except Exception:
            end_time = datetime.utcnow() + timedelta(days=7)
    
    exam_data = {
        'title': data['title'],
        'subject': data['subject'],
        'description': data.get('description', ''),
        'duration_minutes': data.get('duration_minutes', 60),
        'max_mcq_marks': data.get('max_mcq_marks', 30),
        'eligible_classes': data.get('eligible_classes', []),
        'status': 'draft',
        'manually_enabled': False,
        'start_time': start_time,
        'end_time': end_time,
        'academic_term': data.get('academic_term', ''),
        'academic_session': data.get('academic_session', ''),
        'instructions': data.get('instructions', ''),
        'shuffle_questions': data.get('shuffle_questions', True),
        'shuffle_options': data.get('shuffle_options', True),
        'show_correct_answers': data.get('show_correct_answers', False),
        # Randomization from question pool
        'enable_randomization': data.get('enable_randomization', False),
        'mcq_count': data.get('mcq_count', 0)  # 0 means use all questions
    }
    
    new_exam = Exam.create_exam(exam_data)
    
    return jsonify({
        'message': 'Exam created successfully',
        'exam': {
            'id': str(new_exam['_id']),
            'title': new_exam['title'],
            'subject': new_exam['subject'],
            'status': new_exam['status']
        }
    }), 201


@bp.route('/exams/<exam_id>', methods=['GET'])
@admin_required
def get_exam(exam_id):
    """Get a single exam by ID (Admin)"""
    exam = Exam.find_by_id(exam_id)
    
    if not exam:
        return jsonify({'error': 'Exam not found'}), 404
    
    # Get questions count
    mcq_count = mongo.db.questions.count_documents({
        'exam_id': ObjectId(exam_id),
        'question_type': 'mcq',
        'is_active': True
    })
    
    theory_count = mongo.db.questions.count_documents({
        'exam_id': ObjectId(exam_id),
        'question_type': 'theory',
        'is_active': True
    })
    
    return jsonify({
        'message': 'Exam retrieved successfully',
        'exam': {
            'id': str(exam['_id']),
            'title': exam.get('title', ''),
            'subject': exam.get('subject', ''),
            'description': exam.get('description', ''),
            'duration_minutes': exam.get('duration_minutes', 60),
            'max_mcq_marks': exam.get('max_mcq_marks', 30),
            'eligible_classes': exam.get('eligible_classes', []),
            'status': exam.get('status', 'draft'),
            'manually_enabled': exam.get('manually_enabled', False),
            'start_time': exam.get('start_time').isoformat() if exam.get('start_time') else None,
            'end_time': exam.get('end_time').isoformat() if exam.get('end_time') else None,
            'instructions': exam.get('instructions', ''),
            'shuffle_questions': exam.get('shuffle_questions', True),
            'shuffle_options': exam.get('shuffle_options', True),
            'show_correct_answers': exam.get('show_correct_answers', False),
            'mcq_question_count': mcq_count,
            'theory_question_count': theory_count,
            'total_question_count': mcq_count + theory_count,
            'academic_term': exam.get('academic_term', ''),
            'academic_session': exam.get('academic_session', ''),
            'created_at': exam.get('created_at').isoformat() if exam.get('created_at') else None
        }
    }), 200


@bp.route('/exams/<exam_id>', methods=['PUT'])
@admin_required
def update_exam(exam_id):
    """Update an existing exam (Admin)"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    exam = Exam.find_by_id(exam_id)
    if not exam:
        return jsonify({'error': 'Exam not found'}), 404
    
    # Build update data
    update_data = {}
    allowed_fields = [
        'title', 'subject', 'description', 'duration_minutes', 'max_mcq_marks',
        'eligible_classes', 'instructions', 'shuffle_questions', 'shuffle_options',
        'show_correct_answers', 'academic_term', 'academic_session'
    ]
    
    for field in allowed_fields:
        if field in data:
            update_data[field] = data[field]
    
    # Parse dates
    if 'start_time' in data:
        try:
            update_data['start_time'] = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
        except Exception:
            pass
    
    if 'end_time' in data:
        try:
            update_data['end_time'] = datetime.fromisoformat(data['end_time'].replace('Z', '+00:00'))
        except Exception:
            pass
    
    success = Exam.update_exam(exam_id, update_data)
    
    if not success:
        return jsonify({'error': 'Failed to update exam'}), 500
    
    return jsonify({'message': 'Exam updated successfully'}), 200


@bp.route('/exams/<exam_id>/activate', methods=['POST'])
@admin_required
def activate_exam(exam_id):
    """Activate an exam manually (Admin)"""
    exam = Exam.find_by_id(exam_id)
    
    if not exam:
        return jsonify({'error': 'Exam not found'}), 404
    
    success = Exam.update_exam(exam_id, {
        'status': 'active',
        'manually_enabled': True
    })
    
    if not success:
        return jsonify({'error': 'Failed to activate exam'}), 500
    
    return jsonify({'message': 'Exam activated successfully'}), 200


@bp.route('/exams/<exam_id>/deactivate', methods=['POST'])
@admin_required
def deactivate_exam(exam_id):
    """Deactivate an exam (Admin)"""
    exam = Exam.find_by_id(exam_id)
    
    if not exam:
        return jsonify({'error': 'Exam not found'}), 404
    
    success = Exam.update_exam(exam_id, {
        'status': 'draft',
        'manually_enabled': False
    })
    
    if not success:
        return jsonify({'error': 'Failed to deactivate exam'}), 500
    
    return jsonify({'message': 'Exam deactivated successfully'}), 200


@bp.route('/exams/<exam_id>', methods=['DELETE'])
@admin_required
def delete_exam(exam_id):
    """Soft delete an exam (Admin)"""
    exam = Exam.find_by_id(exam_id)
    
    if not exam:
        return jsonify({'error': 'Exam not found'}), 404
    
    success = Exam.update_exam(exam_id, {'is_active': False})
    
    if not success:
        return jsonify({'error': 'Failed to delete exam'}), 500
    
    return jsonify({'message': 'Exam deleted successfully'}), 200


# ==================== QUESTION MANAGEMENT ====================

@bp.route('/exams/<exam_id>/questions', methods=['GET'])
@admin_required
def get_exam_questions(exam_id):
    """Get all questions for an exam (Admin)"""
    exam = Exam.find_by_id(exam_id)
    
    if not exam:
        return jsonify({'error': 'Exam not found'}), 404
    
    question_type = request.args.get('type')
    
    if question_type == 'mcq':
        questions = Question.get_mcq_questions_by_exam(exam_id)
    elif question_type == 'theory':
        questions = Question.get_theory_questions_by_exam(exam_id)
    else:
        questions = Question.get_questions_by_exam(exam_id)
    
    serialized_questions = []
    for q in questions:
        serialized_q = {
            'id': str(q['_id']),
            'question_number': q.get('question_number', 0),
            'question_text': q.get('question_text', ''),
            'question_type': q.get('question_type', 'mcq'),
            'marks': q.get('marks', 1),
            'image_url': q.get('image_url'),
            'explanation': q.get('explanation', ''),
            'created_at': q.get('created_at').isoformat() if q.get('created_at') else None
        }
        
        if q.get('question_type') == 'mcq':
            serialized_q['options'] = q.get('options', [])
            serialized_q['correct_option'] = q.get('correct_option')
        elif q.get('question_type') == 'theory':
            serialized_q['sub_questions'] = q.get('sub_questions', [])
        
        serialized_questions.append(serialized_q)
    
    return jsonify({
        'message': 'Questions retrieved successfully',
        'questions': serialized_questions,
        'count': len(serialized_questions)
    }), 200


@bp.route('/exams/<exam_id>/questions', methods=['POST'])
@admin_required
def create_question(exam_id):
    """Create a new question for an exam (Admin)"""
    exam = Exam.find_by_id(exam_id)
    
    if not exam:
        return jsonify({'error': 'Exam not found'}), 404
    
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    is_valid, error = validate_question_data(data)
    if not is_valid:
        return jsonify({'error': error}), 400
    
    # Get next question number
    existing_count = mongo.db.questions.count_documents({
        'exam_id': ObjectId(exam_id),
        'is_active': True
    })
    
    question_data = {
        'exam_id': ObjectId(exam_id),
        'question_number': existing_count + 1,
        'question_text': data['question_text'],
        'question_type': data['question_type'],
        'marks': data.get('marks', 1),
        'image_url': data.get('image_url'),
        'explanation': data.get('explanation', '')
    }
    
    if data['question_type'] == 'mcq':
        question_data['options'] = data.get('options', [])
        question_data['correct_option'] = data.get('correct_option')
    elif data['question_type'] == 'theory':
        question_data['sub_questions'] = data.get('sub_questions', [])
    
    new_question = Question.create_question(question_data)
    
    return jsonify({
        'message': 'Question created successfully',
        'question': {
            'id': str(new_question['_id']),
            'question_number': new_question['question_number'],
            'question_type': new_question['question_type']
        }
    }), 201


@bp.route('/questions/<question_id>', methods=['PUT'])
@admin_required
def update_question(question_id):
    """Update a question (Admin)"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    question = Question.find_by_id(question_id)
    if not question:
        return jsonify({'error': 'Question not found'}), 404
    
    update_data = {}
    allowed_fields = ['question_text', 'marks', 'image_url', 'explanation', 'options', 'correct_option']
    
    for field in allowed_fields:
        if field in data:
            update_data[field] = data[field]
    
    success = Question.update_question(question_id, update_data)
    
    if not success:
        return jsonify({'error': 'Failed to update question'}), 500
    
    return jsonify({'message': 'Question updated successfully'}), 200


@bp.route('/questions/<question_id>', methods=['DELETE'])
@admin_required
def delete_question(question_id):
    """Soft delete a question (Admin)"""
    question = Question.find_by_id(question_id)
    
    if not question:
        return jsonify({'error': 'Question not found'}), 404
    
    success = Question.delete_question(question_id)
    
    if not success:
        return jsonify({'error': 'Failed to delete question'}), 500
    
    return jsonify({'message': 'Question deleted successfully'}), 200


@bp.route('/exams/<exam_id>/bulk-questions', methods=['POST'])
@admin_required
def bulk_create_questions(exam_id):
    """Bulk create questions for an exam (Admin)"""
    exam = Exam.find_by_id(exam_id)
    
    if not exam:
        return jsonify({'error': 'Exam not found'}), 404
    
    data = request.get_json()
    
    if not data or 'questions' not in data:
        return jsonify({'error': 'Questions data is required'}), 400
    
    questions = data['questions']
    if not isinstance(questions, list):
        return jsonify({'error': 'Questions must be a list'}), 400
    
    # Get current question count
    existing_count = mongo.db.questions.count_documents({
        'exam_id': ObjectId(exam_id),
        'is_active': True
    })
    
    created_count = 0
    errors = []
    
    for i, q_data in enumerate(questions):
        # Validate each question
        is_valid, error = validate_question_data(q_data)
        if not is_valid:
            errors.append(f"Question {i+1}: {error}")
            continue
        
        question_data = {
            'exam_id': ObjectId(exam_id),
            'question_number': existing_count + created_count + 1,
            'question_text': q_data['question_text'],
            'question_type': q_data['question_type'],
            'marks': q_data.get('marks', 1),
            'image_url': q_data.get('image_url'),
            'explanation': q_data.get('explanation', '')
        }
        
        if q_data['question_type'] == 'mcq':
            question_data['options'] = q_data.get('options', [])
            question_data['correct_option'] = q_data.get('correct_option')
        
        Question.create_question(question_data)
        created_count += 1
    
    return jsonify({
        'message': f'Created {created_count} questions',
        'created_count': created_count,
        'errors': errors if errors else None
    }), 201


# ==================== SCORE MANAGEMENT ====================

@bp.route('/exams/<exam_id>/scores', methods=['GET'])
@admin_required
def get_exam_scores(exam_id):
    """Get MCQ scores for an exam (Admin)"""
    exam = Exam.find_by_id(exam_id)
    
    if not exam:
        return jsonify({'error': 'Exam not found'}), 404
    
    class_filter = request.args.get('class_id')
    
    results = ExamResult.get_results_by_exam_and_class(exam_id, class_filter)
    
    export_rows = []
    for result in results:
        mcq_score = result.get('mcq_score', {})
        student = result.get('student', {})
        
        export_rows.append({
            'result_id': str(result['_id']),
            'student_id': str(result['student_id']),
            'admission_number': student.get('admission_number', ''),
            'full_name': student.get('full_name', ''),
            'class_id': student.get('class_id', ''),
            'correct_answers': mcq_score.get('correct_answers', 0),
            'total_questions': mcq_score.get('total_questions', 0),
            'calculated_marks': mcq_score.get('calculated_marks', 0),
            'max_marks': mcq_score.get('max_marks', 30),
            'status': result.get('status', ''),
            'completed_at': result.get('created_at').isoformat() if result.get('created_at') else None
        })
    
    return jsonify({
        'message': 'Scores retrieved successfully',
        'scores': export_rows,
        'exam': {
            'id': str(exam['_id']),
            'title': exam.get('title', ''),
            'subject': exam.get('subject', '')
        },
        'count': len(export_rows)
    }), 200


@bp.route('/exams/<exam_id>/reset-student/<student_id>', methods=['DELETE'])
@admin_required
def reset_student_exam(exam_id, student_id):
    """Reset a student's exam result so they can retake the exam (Admin)"""
    exam = Exam.find_by_id(exam_id)
    
    if not exam:
        return jsonify({'error': 'Exam not found'}), 404
    
    try:
        exam_oid = ObjectId(exam_id)
        student_oid = ObjectId(student_id)
    except Exception:
        return jsonify({'error': 'Invalid ID format'}), 400
    
    # Delete exam result(s) for this student and exam
    result_deleted = mongo.db.exam_results.delete_many({
        'exam_id': exam_oid,
        'student_id': student_oid
    })
    
    # Delete exam session(s) for this student and exam
    session_deleted = mongo.db.exam_sessions.delete_many({
        'exam_id': exam_oid,
        'student_id': student_oid
    })
    
    if result_deleted.deleted_count == 0 and session_deleted.deleted_count == 0:
        return jsonify({'error': 'No exam records found for this student'}), 404
    
    return jsonify({
        'message': 'Student exam reset successfully',
        'results_deleted': result_deleted.deleted_count,
        'sessions_deleted': session_deleted.deleted_count
    }), 200


# ==================== STUDENT EXAM ENDPOINTS ====================

@bp.route('/student/available-exams', methods=['GET'])
@jwt_required()
def get_available_exams():
    """Get available exams for the logged-in student"""
    claims = get_jwt()
    user_id = get_jwt_identity()
    
    if claims.get('user_type') != 'student_exam':
        return jsonify({'error': 'Exam mode access required'}), 403
    
    student_class = claims.get('class_id', '')
    
    # Debug logging
    print(f"[DEBUG] Student class from JWT: '{student_class}'")
    print(f"[DEBUG] User ID: {user_id}")
    
    if not student_class:
        return jsonify({'error': 'Student class not found'}), 400
    
    exams = Exam.get_active_exams_for_student(student_class, student_id=user_id)
    
    # Debug: log number of exams found
    print(f"[DEBUG] Found {len(exams)} exams for student class '{student_class}'")
    
    serialized_exams = []
    for exam in exams:
        # Get active question counts
        mcq_questions_count = mongo.db.questions.count_documents({
            'exam_id': exam['_id'],
            'question_type': 'mcq',
            'is_active': True
        })
        
        theory_questions_count = mongo.db.questions.count_documents({
            'exam_id': exam['_id'],
            'question_type': 'theory',
            'is_active': True
        })
        
        # Determine how many MCQs will effectively be shown
        effective_mcq_count = mcq_questions_count
        if exam.get('enable_randomization', False) and exam.get('mcq_count', 0) > 0:
            effective_mcq_count = min(mcq_questions_count, exam.get('mcq_count', 0))
        
        serialized_exams.append({
            'id': str(exam['_id']),
            'title': exam.get('title', ''),
            'subject': exam.get('subject', ''),
            'description': exam.get('description', ''),
            'duration_minutes': exam.get('duration_minutes', 60),
            'question_count': effective_mcq_count + theory_questions_count,
            'mcq_count': effective_mcq_count,
            'theory_count': theory_questions_count,
            'instructions': exam.get('instructions', ''),
            'has_mcq': mcq_questions_count > 0,
            'has_theory': theory_questions_count > 0
        })
    
    return jsonify({
        'message': 'Available exams retrieved',
        'exams': serialized_exams
    }), 200


@bp.route('/student/start-exam/<exam_id>', methods=['POST'])
@jwt_required()
def start_exam(exam_id):
    """Start an exam session for the student"""
    claims = get_jwt()
    user_id = get_jwt_identity()
    
    if claims.get('user_type') != 'student_exam':
        return jsonify({'error': 'Exam mode access required'}), 403
    
    # Check if exam exists and is available
    exam = Exam.find_by_id(exam_id)
    if not exam:
        return jsonify({'error': 'Exam not found'}), 404
    
    # Check if student already has an active session
    existing_session = ExamSession.find_active_session(user_id, exam_id)
    if existing_session:
        # Resume existing session - use stored question IDs if randomized
        selected_question_ids = existing_session.get('selected_question_ids')
        
        if selected_question_ids:
            # Randomization was used - get only the selected questions
            questions = list(mongo.db.questions.find({
                '_id': {'$in': [ObjectId(qid) for qid in selected_question_ids]},
                'is_active': True
            }).sort('question_number', 1))
        else:
            # No randomization - get all MCQ questions
            questions = Question.get_mcq_questions_by_exam(exam_id)
        
        return jsonify({
            'message': 'Resuming existing session',
            'session_id': str(existing_session['_id']),
            'exam': {
                'id': str(exam['_id']),
                'title': exam.get('title', ''),
                'duration_minutes': exam.get('duration_minutes', 60),
                'instructions': exam.get('instructions', '')
            },
            'questions': serialize_questions_for_student(questions),
            'answers': existing_session.get('answers', {}),
            'start_time': existing_session['start_time'].isoformat()
        }), 200
    
    # Check if student already completed this exam
    existing_result = mongo.db.exam_results.find_one({
        'student_id': ObjectId(user_id),
        'exam_id': ObjectId(exam_id),
        'status': {'$in': ['completed', 'mcq_completed']}
    })
    
    if existing_result:
        return jsonify({'error': 'You have already completed this exam'}), 400
    
    # Get all MCQ questions from the pool
    all_mcq_questions = Question.get_mcq_questions_by_exam(exam_id)
    
    # Apply randomization if enabled
    enable_randomization = exam.get('enable_randomization', False)
    mcq_count = exam.get('mcq_count', 0)
    selected_question_ids = None
    
    if enable_randomization and mcq_count > 0 and len(all_mcq_questions) > mcq_count:
        # Randomly select mcq_count questions using cryptographic randomness
        selected_questions = []
        pool = list(all_mcq_questions)  # Copy to avoid modifying original
        
        for _ in range(mcq_count):
            if not pool:
                break
            # Use secrets.randbelow for cryptographic security
            idx = secrets.randbelow(len(pool))
            selected_questions.append(pool.pop(idx))
        
        # Sort by question number for consistent display
        selected_questions.sort(key=lambda q: q.get('question_number', 0))
        questions = selected_questions
        selected_question_ids = [str(q['_id']) for q in selected_questions]
    else:
        # Use all questions (no randomization or pool not larger than count)
        questions = all_mcq_questions
    
    # Create new session with selected question IDs if randomized
    session_data = {
        'student_id': ObjectId(user_id),
        'exam_id': ObjectId(exam_id),
        'admission_number': claims.get('admission_number'),
        'full_name': claims.get('full_name'),
        'class_id': claims.get('class_id'),
        'selected_question_ids': selected_question_ids  # Store for resume consistency
    }
    
    session = ExamSession.create_session(session_data)
    
    return jsonify({
        'message': 'Exam session started',
        'session_id': str(session['_id']),
        'exam': {
            'id': str(exam['_id']),
            'title': exam.get('title', ''),
            'duration_minutes': exam.get('duration_minutes', 60),
            'instructions': exam.get('instructions', '')
        },
        'questions': serialize_questions_for_student(questions),
        'start_time': session['start_time'].isoformat()
    }), 201


@bp.route('/student/submit-answer', methods=['POST'])
@jwt_required()
def submit_answer():
    """Submit an answer for a question"""
    claims = get_jwt()
    
    if claims.get('user_type') != 'student_exam':
        return jsonify({'error': 'Exam mode access required'}), 403
    
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    session_id = data.get('session_id')
    question_id = data.get('question_id')
    selected_option = data.get('selected_option')
    
    if not session_id or not question_id or selected_option is None:
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Verify session exists and is active
    session = ExamSession.find_by_id(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    
    if session.get('status') != 'in_progress':
        return jsonify({'error': 'Session is not active'}), 400
    
    # Submit the answer
    success, is_correct = ExamSession.submit_mcq_answer(session_id, question_id, selected_option)
    
    if not success:
        return jsonify({'error': 'Failed to submit answer'}), 500
    
    return jsonify({
        'message': 'Answer submitted successfully',
        'question_id': question_id,
        'selected_option': selected_option
    }), 200


@bp.route('/student/complete-exam', methods=['POST'])
@jwt_required()
def complete_exam():
    """Complete an exam session and calculate score"""
    claims = get_jwt()
    user_id = get_jwt_identity()
    
    if claims.get('user_type') != 'student_exam':
        return jsonify({'error': 'Exam mode access required'}), 403
    
    data = request.get_json()
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({'error': 'Session ID is required'}), 400
    
    # Get session
    session = ExamSession.find_by_id(session_id)
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    
    if session.get('status') != 'in_progress':
        return jsonify({'error': 'Session is not active'}), 400
    
    # Get exam for max marks
    exam = Exam.find_by_id(session['exam_id'])
    max_mcq_marks = exam.get('max_mcq_marks', 30) if exam else 30
    
    # Calculate MCQ score
    mcq_score = ExamResult.calculate_mcq_score(session, max_mcq_marks)
    
    # Complete the session
    ExamSession.complete_session(session_id, {'mcq_score': mcq_score})
    
    # Create exam result
    result_data = {
        'student_id': ObjectId(user_id),
        'exam_id': session['exam_id'],
        'session_id': ObjectId(session_id),
        'admission_number': claims.get('admission_number'),
        'full_name': claims.get('full_name'),
        'class_id': claims.get('class_id'),
        'mcq_score': mcq_score,
        'status': 'mcq_completed'
    }
    
    result = ExamResult.create_result(result_data)
    
    return jsonify({
        'message': 'Exam completed successfully',
        'result': {
            'id': str(result['_id']),
            'correct_answers': mcq_score['correct_answers'],
            'total_questions': mcq_score['total_questions'],
            'calculated_marks': mcq_score['calculated_marks'],
            'max_marks': mcq_score['max_marks'],
            'percentage': round((mcq_score['correct_answers'] / mcq_score['total_questions'] * 100), 1) if mcq_score['total_questions'] > 0 else 0
        }
    }), 200


@bp.route('/student/session-status/<session_id>', methods=['GET'])
@jwt_required()
def get_session_status(session_id):
    """Get current session status and answers"""
    claims = get_jwt()
    
    if claims.get('user_type') != 'student_exam':
        return jsonify({'error': 'Exam mode access required'}), 403
    
    session = ExamSession.find_by_id(session_id)
    
    if not session:
        return jsonify({'error': 'Session not found'}), 404
    
    return jsonify({
        'message': 'Session status retrieved',
        'session': {
            'id': str(session['_id']),
            'status': session.get('status'),
            'start_time': session['start_time'].isoformat() if session.get('start_time') else None,
            'answers': session.get('answers', {}),
            'answered_count': len(session.get('answers', {}))
        }
    }), 200


def serialize_questions_for_student(questions):
    """Serialize questions for student view (without correct answers)"""
    serialized = []
    for q in questions:
        serialized_q = {
            'id': str(q['_id']),
            'question_number': q.get('question_number', 0),
            'question_text': q.get('question_text', ''),
            'question_type': q.get('question_type', 'mcq'),
            'marks': q.get('marks', 1),
            'image_url': q.get('image_url')
        }
        
        if q.get('question_type') == 'mcq':
            serialized_q['options'] = q.get('options', [])
            # Do NOT include correct_option for students
        elif q.get('question_type') == 'theory':
            # Include sub-questions for theory
            if q.get('sub_questions'):
                serialized_q['sub_questions'] = q.get('sub_questions', [])
        
        serialized.append(serialized_q)
    
    return serialized


# ==================== THEORY EXAM ENDPOINTS ====================

@bp.route('/student/start-theory-exam/<exam_id>', methods=['POST'])
@jwt_required()
def start_theory_exam(exam_id):
    """Start or resume a theory exam session for the student"""
    claims = get_jwt()
    user_id = get_jwt_identity()
    
    if claims.get('user_type') != 'student_exam':
        return jsonify({'error': 'Exam mode access required'}), 403
    
    # Check if exam exists
    exam = Exam.find_by_id(exam_id)
    if not exam:
        return jsonify({'error': 'Exam not found'}), 404
    
    # Check for existing theory session
    existing_session = mongo.db.theory_sessions.find_one({
        'student_id': ObjectId(user_id),
        'exam_id': ObjectId(exam_id),
        'status': 'active'
    })
    
    # Get theory questions only
    theory_questions = list(mongo.db.questions.find({
        'exam_id': ObjectId(exam_id),
        'question_type': 'theory',
        'is_active': True
    }).sort('question_number', 1))
    
    if existing_session:
        # Calculate time remaining
        elapsed = (datetime.utcnow() - existing_session['start_time']).total_seconds()
        duration_seconds = exam.get('duration_minutes', 60) * 60
        time_remaining = max(0, duration_seconds - elapsed)
        
        return jsonify({
            'message': 'Resuming theory session',
            'session_id': str(existing_session['_id']),
            'exam_title': exam.get('title', ''),
            'duration_minutes': exam.get('duration_minutes', 60),
            'questions': serialize_questions_for_student(theory_questions),
            'answers': existing_session.get('answers', {}),
            'time_remaining': int(time_remaining)
        }), 200
    
    # Create new theory session
    session_data = {
        'student_id': ObjectId(user_id),
        'exam_id': ObjectId(exam_id),
        'admission_number': claims.get('admission_number'),
        'full_name': claims.get('full_name'),
        'class_id': claims.get('class_id'),
        'start_time': datetime.utcnow(),
        'status': 'active',
        'answers': {'main': {}, 'sub': {}}
    }
    
    result = mongo.db.theory_sessions.insert_one(session_data)
    session_data['_id'] = result.inserted_id
    
    return jsonify({
        'message': 'Theory exam session started',
        'session_id': str(session_data['_id']),
        'exam_title': exam.get('title', ''),
        'duration_minutes': exam.get('duration_minutes', 60),
        'questions': serialize_questions_for_student(theory_questions),
        'time_remaining': exam.get('duration_minutes', 60) * 60
    }), 201


@bp.route('/student/complete-theory-exam', methods=['POST'])
@jwt_required()
def complete_theory_exam():
    """Submit theory exam answers"""
    claims = get_jwt()
    user_id = get_jwt_identity()
    
    if claims.get('user_type') != 'student_exam':
        return jsonify({'error': 'Exam mode access required'}), 403
    
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    session_id = data.get('session_id')
    main_answers = data.get('main_answers', {})
    sub_answers = data.get('sub_answers', {})
    
    if not session_id:
        return jsonify({'error': 'Session ID required'}), 400
    
    # Find and update session
    session = mongo.db.theory_sessions.find_one({
        '_id': ObjectId(session_id),
        'student_id': ObjectId(user_id),
        'status': 'active'
    })
    
    if not session:
        return jsonify({'error': 'Session not found or already completed'}), 404
    
    # Update session with answers and mark as completed
    mongo.db.theory_sessions.update_one(
        {'_id': ObjectId(session_id)},
        {
            '$set': {
                'status': 'completed',
                'completed_at': datetime.utcnow(),
                'answers': {
                    'main': main_answers,
                    'sub': sub_answers
                }
            }
        }
    )
    
    # Create or update exam result with theory answers
    existing_result = mongo.db.exam_results.find_one({
        'student_id': ObjectId(user_id),
        'exam_id': session['exam_id']
    })
    
    if existing_result:
        # Update existing result (MCQ already completed)
        mongo.db.exam_results.update_one(
            {'_id': existing_result['_id']},
            {
                '$set': {
                    'theory_answers': {'main': main_answers, 'sub': sub_answers},
                    'theory_status': 'submitted',
                    'status': 'completed'
                }
            }
        )
    else:
        # Create new result (theory only)
        result_data = {
            'student_id': ObjectId(user_id),
            'exam_id': session['exam_id'],
            'admission_number': claims.get('admission_number'),
            'full_name': claims.get('full_name'),
            'class_id': claims.get('class_id'),
            'theory_answers': {'main': main_answers, 'sub': sub_answers},
            'theory_status': 'submitted',
            'status': 'theory_completed',
            'created_at': datetime.utcnow()
        }
        mongo.db.exam_results.insert_one(result_data)
    
    return jsonify({
        'message': 'Theory exam submitted successfully'
    }), 200
