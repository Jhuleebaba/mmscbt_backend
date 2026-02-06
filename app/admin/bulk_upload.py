from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
import os
import tempfile
from typing import Dict, List, Any
import logging
from bson import ObjectId

from app.models.exam import Question, Exam
try:
    from app.utils.document_parser import DocumentParser, QuestionValidator
    DOCUMENT_PARSER_AVAILABLE = True
except ImportError:
    DOCUMENT_PARSER_AVAILABLE = False
    DocumentParser = None
    QuestionValidator = None
from app.utils.decorators import admin_required
from app import mongo

logger = logging.getLogger(__name__)

# Enable automatic image extraction from documents
from app.utils.document_parser_image_patch import enable_automatic_image_extraction
enable_automatic_image_extraction()
logger.info("Automatic image extraction enabled for exam bulk uploads")

# Enable snapshot-based parsing for ultra-flexible question parsing
from app.utils.snapshot_parser import enable_snapshot_parsing
enable_snapshot_parsing()
logger.info("Snapshot-based parsing enabled")

bp = Blueprint('bulk_upload', __name__)

class BulkQuestionUploader:
    """Handle bulk question uploads with comprehensive processing."""
    
    def __init__(self):
        if not DOCUMENT_PARSER_AVAILABLE:
            raise ImportError("Document parsing dependencies not available. Install python-docx, PyPDF2, etc.")
        self.parser = DocumentParser()
        self.validator = QuestionValidator()
        self.max_file_size = 50 * 1024 * 1024  # 50MB
        self.allowed_extensions = {'.docx', '.doc', '.pdf', '.html', '.htm', '.xlsx', '.xls'}
    
    def process_upload(self, file, exam_id: str, question_type: str = 'auto', 
                      validation_mode: str = 'strict') -> Dict[str, Any]:
        """
        Process uploaded file and extract questions.
        
        Args:
            file: Uploaded file object
            exam_id: Target exam ID
            question_type: 'mcq', 'theory', or 'auto'
            validation_mode: 'strict' or 'lenient'
        
        Returns:
            Processing result with questions and statistics
        """
        try:
            # Validate file
            validation_result = self._validate_file(file)
            if not validation_result['valid']:
                return validation_result
            
            # Validate exam
            exam = Exam.find_by_id(exam_id)
            if not exam:
                return {'success': False, 'error': 'Exam not found'}
            
            # Read file content
            file_content = file.read()
            filename = secure_filename(file.filename)
            
            # Parse document
            parse_result = self.parser.parse_document(file_content, filename, question_type)
            
            # Process and validate questions
            processing_result = self._process_parsed_questions(
                parse_result, exam_id, validation_mode
            )
            
            return {
                'success': True,
                'exam_id': exam_id,
                'filename': filename,
                'format': parse_result.get('format'),
                **processing_result
            }
            
        except Exception as e:
            logger.error(f"Error processing upload: {str(e)}")
            return {
                'success': False,
                'error': f'Processing failed: {str(e)}'
            }
    
    def _validate_file(self, file) -> Dict[str, Any]:
        """Validate uploaded file."""
        if not file:
            return {'valid': False, 'error': 'No file provided'}
        
        if not file.filename:
            return {'valid': False, 'error': 'No filename provided'}
        
        # Check file extension
        filename = secure_filename(file.filename)
        file_ext = os.path.splitext(filename.lower())[1]
        
        if file_ext not in self.allowed_extensions:
            return {
                'valid': False,
                'error': f'Unsupported file type: {file_ext}. Supported: {", ".join(self.allowed_extensions)}'
            }
        
        # Check file size (if available)
        if hasattr(file, 'content_length') and file.content_length:
            if file.content_length > self.max_file_size:
                return {
                    'valid': False,
                    'error': f'File too large. Maximum size: {self.max_file_size // (1024*1024)}MB'
                }
        
        return {'valid': True}
    
    def _process_parsed_questions(self, parse_result: Dict, exam_id: str, 
                                validation_mode: str) -> Dict[str, Any]:
        """Process and validate parsed questions with instruction support."""
        mcq_questions = parse_result.get('mcq_questions', [])
        theory_questions = parse_result.get('theory_questions', [])
        instructions = parse_result.get('instructions', [])
        
        # Validate instructions first
        instruction_validation = self._validate_instructions_batch(instructions)
        
        # Validate questions
        mcq_validation = self._validate_questions_batch(mcq_questions, 'mcq', validation_mode)
        theory_validation = self._validate_questions_batch(theory_questions, 'theory', validation_mode)
        
        # Prepare statistics
        stats = {
            'total_parsed': len(mcq_questions) + len(theory_questions),
            'mcq_parsed': len(mcq_questions),
            'theory_parsed': len(theory_questions),
            'mcq_valid': len(mcq_validation['valid']),
            'theory_valid': len(theory_validation['valid']),
            'mcq_invalid': len(mcq_validation['invalid']),
            'theory_invalid': len(theory_validation['invalid']),
            'total_valid': len(mcq_validation['valid']) + len(theory_validation['valid']),
            'total_invalid': len(mcq_validation['invalid']) + len(theory_validation['invalid']),
            'instructions_parsed': len(instructions),
            'instructions_valid': len(instruction_validation['valid']),
            'instructions_invalid': len(instruction_validation['invalid'])
        }
        
        # Collect all validation errors
        all_errors = (mcq_validation['errors'] + theory_validation['errors'] + 
                     instruction_validation['errors'])
        all_warnings = parse_result.get('warnings', [])
        
        return {
            'statistics': stats,
            'valid_questions': {
                'mcq': mcq_validation['valid'],
                'theory': theory_validation['valid']
            },
            'invalid_questions': {
                'mcq': mcq_validation['invalid'],
                'theory': theory_validation['invalid']
            },
            'valid_instructions': instruction_validation['valid'],
            'invalid_instructions': instruction_validation['invalid'],
            'errors': all_errors,
            'warnings': all_warnings,
            'preview': self._generate_preview_with_instructions(
                mcq_validation['valid'], 
                theory_validation['valid'],
                instruction_validation['valid']
            )
        }
    
    def _validate_questions_batch(self, questions: List[Dict], q_type: str, 
                                validation_mode: str) -> Dict[str, Any]:
        """Validate a batch of questions."""
        valid_questions = []
        invalid_questions = []
        errors = []
        
        for i, question in enumerate(questions):
            try:
                if q_type == 'mcq':
                    is_valid, question_errors = self.validator.validate_mcq_question(question)
                else:
                    is_valid, question_errors = self.validator.validate_theory_question(question)
                
                if is_valid or validation_mode == 'lenient':
                    if is_valid:
                        valid_questions.append(question)
                    else:
                        # In lenient mode, try to fix common issues
                        fixed_question = self._attempt_fix_question(question, q_type)
                        if fixed_question:
                            valid_questions.append(fixed_question)
                            errors.append(f"{q_type.upper()} Question {i+1}: Fixed automatically - {'; '.join(question_errors)}")
                        else:
                            invalid_questions.append({'question': question, 'errors': question_errors})
                            errors.append(f"{q_type.upper()} Question {i+1}: {'; '.join(question_errors)}")
                else:
                    invalid_questions.append({'question': question, 'errors': question_errors})
                    errors.append(f"{q_type.upper()} Question {i+1}: {'; '.join(question_errors)}")
                    
            except Exception as e:
                invalid_questions.append({'question': question, 'errors': [str(e)]})
                errors.append(f"{q_type.upper()} Question {i+1}: Validation error - {str(e)}")
        
        return {
            'valid': valid_questions,
            'invalid': invalid_questions,
            'errors': errors
        }
    
    def _attempt_fix_question(self, question: Dict, q_type: str) -> Dict[str, Any]:
        """Attempt to fix common issues in questions."""
        fixed_question = question.copy()
        
        try:
            if q_type == 'mcq':
                # Fix missing correct option
                if 'correct_option' not in fixed_question:
                    fixed_question['correct_option'] = 0
                
                # Ensure minimum options
                options = fixed_question.get('options', [])
                while len(options) < 2:
                    options.append(f"Option {len(options) + 1}")
                fixed_question['options'] = options
                
                # Ensure marks
                if not fixed_question.get('marks') or fixed_question['marks'] <= 0:
                    fixed_question['marks'] = 1
            
            elif q_type == 'theory':
                # Fix missing sub-questions
                if not fixed_question.get('sub_questions'):
                    fixed_question['sub_questions'] = [{
                        'sub_number': 'a',
                        'sub_text': fixed_question.get('question_text', 'Default question'),
                        'sub_marks': fixed_question.get('marks', 1)
                    }]
                
                # Ensure marks consistency
                total_sub_marks = sum(sq.get('sub_marks', 1) for sq in fixed_question['sub_questions'])
                fixed_question['marks'] = total_sub_marks
            
            # Validate the fixed question
            if q_type == 'mcq':
                is_valid, _ = self.validator.validate_mcq_question(fixed_question)
            else:
                is_valid, _ = self.validator.validate_theory_question(fixed_question)
            
            return fixed_question if is_valid else None
            
        except Exception:
            return None
    
    def _validate_instructions_batch(self, instructions: List[Dict]) -> Dict[str, Any]:
        """Validate a batch of instructions."""
        valid_instructions = []
        invalid_instructions = []
        errors = []
        
        for i, instruction in enumerate(instructions):
            try:
                is_valid, instruction_errors = self.validator.validate_instruction(instruction)
                
                if is_valid:
                    valid_instructions.append(instruction)
                else:
                    invalid_instructions.append({'instruction': instruction, 'errors': instruction_errors})
                    errors.append(f"Instruction {i+1} ({instruction.get('title', 'Untitled')}): {'; '.join(instruction_errors)}")
                    
            except Exception as e:
                invalid_instructions.append({'instruction': instruction, 'errors': [str(e)]})
                errors.append(f"Instruction {i+1}: Validation error - {str(e)}")
        
        return {
            'valid': valid_instructions,
            'invalid': invalid_instructions,
            'errors': errors
        }
    
    def _generate_preview_with_instructions(self, mcq_questions: List[Dict], 
                                          theory_questions: List[Dict],
                                          instructions: List[Dict]) -> Dict[str, Any]:
        """Generate preview of questions and instructions for user review."""
        preview = {
            'mcq_preview': mcq_questions[:3],  # First 3 MCQ questions
            'theory_preview': theory_questions[:3],  # First 3 Theory questions
            'instructions_preview': instructions[:5],  # First 5 instructions
            'has_more_mcq': len(mcq_questions) > 3,
            'has_more_theory': len(theory_questions) > 3,
            'has_more_instructions': len(instructions) > 5
        }
        
        return preview
    
    def _generate_preview(self, mcq_questions: List[Dict], theory_questions: List[Dict]) -> Dict[str, Any]:
        """Generate preview of questions for user review (legacy method)."""
        preview = {
            'mcq_preview': mcq_questions[:3],  # First 3 MCQ questions
            'theory_preview': theory_questions[:3],  # First 3 Theory questions
            'has_more_mcq': len(mcq_questions) > 3,
            'has_more_theory': len(theory_questions) > 3
        }
        
        return preview
    
    def save_questions_to_exam(self, valid_data: Dict[str, Any], exam_id: str) -> Dict[str, Any]:
        """Save validated questions and instructions to the exam."""
        try:
            # Handle both old format (just questions) and new format (questions + instructions)
            if 'mcq' in valid_data and 'theory' in valid_data:
                # Old format - just questions
                mcq_questions = valid_data.get('mcq', [])
                theory_questions = valid_data.get('theory', [])
                instructions = []
            else:
                # New format - questions and instructions
                mcq_questions = valid_data.get('valid_questions', {}).get('mcq', [])
                theory_questions = valid_data.get('valid_questions', {}).get('theory', [])
                instructions = valid_data.get('valid_instructions', [])
            
            # Get current exam data
            exam = Exam.find_by_id(exam_id)
            if not exam:
                return {'success': False, 'error': 'Exam not found'}
            
            # Save instructions first and create a mapping
            instruction_map = {}
            saved_instructions = []
            
            for instruction in instructions:
                try:
                    instruction_data = {
                        'exam_id': ObjectId(exam_id),
                        'id': instruction['id'],  # Use 'id' not 'instruction_id'
                        'type': instruction['type'],
                        'title': instruction['title'],
                        'instruction_text': instruction.get('instruction_text', ''),
                        'full_text': instruction.get('full_text', ''),
                        'applies_to': instruction['applies_to'],
                        'start_question': instruction.get('start_question'),
                        'end_question': instruction.get('end_question'),
                        'component': instruction.get('component'),
                        'identifier': instruction.get('identifier'),
                        'order': instruction.get('order', 0)
                    }
                    
                    # Save to exam_instructions collection
                    result = mongo.db.exam_instructions.insert_one(instruction_data)
                    instruction_data['_id'] = result.inserted_id
                    saved_instructions.append(instruction_data)
                    instruction_map[instruction['id']] = instruction_data
                    
                    logger.info(f"Successfully saved instruction: {instruction['title']}")
                    
                except Exception as e:
                    logger.error(f"Failed to save instruction {instruction.get('title', 'Unknown')}: {str(e)}")
            
            # Get existing question counts for numbering
            existing_questions = Question.get_questions_by_exam(exam_id)
            mcq_count = len([q for q in existing_questions if q.get('question_type') == 'mcq'])
            theory_count = len([q for q in existing_questions if q.get('question_type') == 'theory'])
            
            saved_mcq = []
            saved_theory = []
            errors = []
            
            # Enforce equal marks for all MCQ questions
            if mcq_questions:
                # Calculate equal marks: 30 total marks divided by number of MCQ questions
                total_mcq_marks = 30
                mcq_marks_per_question = max(1, total_mcq_marks // len(mcq_questions))
                logger.info(f"Enforcing equal MCQ marks: {mcq_marks_per_question} marks per question ({len(mcq_questions)} questions)")
            
            # Save MCQ questions
            for i, question in enumerate(mcq_questions):
                try:
                    question_data = {
                        'exam_id': ObjectId(exam_id),  # Convert to ObjectId
                        'question_number': mcq_count + i + 1,
                        'question_text': question['question_text'],
                        'question_type': 'mcq',
                        'options': question['options'],
                        'correct_option': question['correct_option'],
                        'marks': mcq_marks_per_question if mcq_questions else question['marks'],  # Use equal marks
                        'instruction_id': question.get('instruction_id'),
                        # Include image and rich content fields
                        'question_image': question.get('question_image'),
                        'option_images': question.get('option_images', []),
                        'content_type': question.get('content_type', 'text'),
                        'has_rich_content': question.get('has_rich_content', False),
                        'images': question.get('images', [])
                    }
                    
                    created_question = Question.create_question(question_data)
                    saved_mcq.append(created_question)
                    logger.info(f"Successfully saved MCQ question {i+1}")
                    
                except Exception as e:
                    logger.error(f"Failed to save MCQ question {i+1}: {str(e)}")
                    errors.append(f"Failed to save MCQ question {i+1}: {str(e)}")
            
            # Save Theory questions
            for i, question in enumerate(theory_questions):
                try:
                    question_data = {
                        'exam_id': ObjectId(exam_id),  # Convert to ObjectId
                        'question_number': theory_count + i + 1,
                        'question_text': question.get('question_text', ''),
                        'question_type': 'theory',
                        'sub_questions': question['sub_questions'],
                        'marks': question['marks'],
                        'instruction_id': question.get('instruction_id'),
                        # Include image and rich content fields
                        'question_image': question.get('question_image'),
                        'option_images': question.get('option_images', []),
                        'content_type': question.get('content_type', 'text'),
                        'has_rich_content': question.get('has_rich_content', False),
                        'images': question.get('images', [])
                    }
                    
                    created_question = Question.create_question(question_data)
                    saved_theory.append(created_question)
                    logger.info(f"Successfully saved Theory question {i+1}")
                    
                except Exception as e:
                    logger.error(f"Failed to save Theory question {i+1}: {str(e)}")
                    errors.append(f"Failed to save Theory question {i+1}: {str(e)}")
            
            # Update exam metadata (recalculate pools rather than mutating configured limits)
            update_data = {}
            if saved_mcq:
                mcq_pool_count = mongo.db.questions.count_documents({
                    'exam_id': ObjectId(exam_id),
                    'question_type': 'mcq',
                    'is_active': True
                })
                update_data.update({
                    'mcq_pool_count': mcq_pool_count,
                    'has_mcq': mcq_pool_count > 0
                })

            if saved_theory:
                theory_pool_count = mongo.db.questions.count_documents({
                    'exam_id': ObjectId(exam_id),
                    'question_type': 'theory',
                    'is_active': True
                })
                update_data.update({
                    'theory_pool_count': theory_pool_count,
                    'has_theory': theory_pool_count > 0
                })

            if saved_instructions:
                update_data['has_instructions'] = True

            if update_data:
                Exam.update_exam(exam_id, update_data)
            
            logger.info(f"Bulk upload completed: {len(saved_mcq)} MCQ, {len(saved_theory)} Theory questions, {len(saved_instructions)} instructions saved")
            
            return {
                'success': True,
                'saved_mcq': len(saved_mcq),
                'saved_theory': len(saved_theory),
                'saved_instructions': len(saved_instructions),
                'total_saved': len(saved_mcq) + len(saved_theory),
                'errors': errors
            }
            
        except Exception as e:
            logger.error(f"Error saving questions and instructions: {str(e)}")
            return {
                'success': False,
                'error': f'Failed to save questions and instructions: {str(e)}'
            }


# Initialize the uploader
uploader = BulkQuestionUploader()


@bp.route('/admin/exam/<exam_id>/bulk-upload', methods=['POST'])
@admin_required
def bulk_upload_questions(exam_id):
    """
    Bulk upload questions from document files.
    Supports DOCX, DOC, PDF, HTML, and Excel formats.
    """
    try:
        if not DOCUMENT_PARSER_AVAILABLE:
            return jsonify({
                'success': False,
                'error': 'Document parsing feature not available. Missing dependencies: python-docx, PyPDF2, etc.'
            }), 503
            
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Get upload parameters
        question_type = request.form.get('question_type', 'auto')  # mcq, theory, auto
        validation_mode = request.form.get('validation_mode', 'strict')  # strict, lenient
        
        # Validate parameters
        if question_type not in ['mcq', 'theory', 'auto']:
            return jsonify({'error': 'Invalid question type'}), 400
        
        if validation_mode not in ['strict', 'lenient']:
            return jsonify({'error': 'Invalid validation mode'}), 400
        
        # Enable debug logging for document parsing
        import logging
        logging.getLogger('app.utils.document_parser').setLevel(logging.DEBUG)
        
        logger.info(f"Starting bulk upload for exam {exam_id}, file: {file.filename}, type: {question_type}, validation: {validation_mode}")
        
        # Process upload
        result = uploader.process_upload(file, exam_id, question_type, validation_mode)
        
        if not result['success']:
            logger.error(f"Upload processing failed: {result['error']}")
            return jsonify({'error': result['error']}), 400
        
        logger.info(f"Upload processed successfully: {result.get('statistics', {})}")
        
        return jsonify({
            'message': 'File processed successfully',
            'data': result
        }), 200
        
    except Exception as e:
        logger.error(f"Bulk upload error: {str(e)}")
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500


@bp.route('/admin/exam/<exam_id>/bulk-upload/confirm', methods=['POST'])
@admin_required
def confirm_bulk_upload(exam_id):
    """
    Confirm and save the bulk uploaded questions and instructions to the exam.
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Handle both old format (just valid_questions) and new format (with instructions)
        if 'valid_questions' in data and ('valid_instructions' in data or 'instructions' in data):
            # New format with instructions
            valid_data = {
                'valid_questions': data['valid_questions'],
                'valid_instructions': data.get('valid_instructions', data.get('instructions', []))
            }
        elif 'valid_questions' in data:
            # Old format - just questions
            valid_data = data['valid_questions']
        else:
            return jsonify({'error': 'No valid questions data provided'}), 400
        
        # Save questions and instructions to exam
        result = uploader.save_questions_to_exam(valid_data, exam_id)
        
        if not result['success']:
            return jsonify({'error': result['error']}), 400
        
        message = f"Successfully saved {result['total_saved']} questions"
        if result.get('saved_instructions', 0) > 0:
            message += f" and {result['saved_instructions']} instructions"
        
        return jsonify({
            'message': message,
            'data': result
        }), 200
        
    except Exception as e:
        logger.error(f"Confirm upload error: {str(e)}")
        return jsonify({'error': f'Save failed: {str(e)}'}), 500


@bp.route('/admin/bulk-upload/supported-formats', methods=['GET'])
@admin_required
def get_supported_formats():
    """Get information about supported file formats and their requirements."""
    
    format_info = {
        'supported_formats': [
            {
                'extension': '.docx',
                'name': 'Microsoft Word Document',
                'description': 'Preferred format with full rich text support, flexible question parsing, and instruction detection',
                'features': ['Rich text formatting', 'Images', 'Mathematical symbols', 'Flexible question patterns', 'Auto-detection', 'Instruction parsing'],
                'requirements': [
                    'Questions can start with numbers (1., 1), 1:, 1-, 1 What is...) or Q1:, Q1., Question 1',
                    'MCQ options can use A., A), A,, A:, A-, a., a), (a), (A), 1., 2., etc.',
                    'Mark correct answers with *, ✓, √, (correct), [answer], (right), ans, or make it bold',
                    'Theory sub-questions can use a), b), i), ii), (a), (i), a., i., etc.',
                    'Marks can be [5 marks], (10 points), 5pts, 5m, 5p, marks: 5, or just 5',
                    'Instructions use clear headings (INSTRUCTIONS:, SECTION A:, SYNONYMS:, etc.)'
                ]
            },
            {
                'extension': '.doc',
                'name': 'Legacy Word Document',
                'description': 'Converted to HTML for processing with flexible patterns and instruction support',
                'features': ['Basic formatting', 'Flexible question patterns', 'Auto-detection', 'Instruction parsing'],
                'requirements': ['Same flexible patterns as DOCX but limited formatting preservation']
            },
            {
                'extension': '.pdf',
                'name': 'PDF Document',
                'description': 'Text extraction with flexible pattern matching and basic instruction detection',
                'features': ['Basic text extraction', 'Flexible question patterns', 'Auto-detection', 'Simple instruction parsing'],
                'requirements': ['Clear text structure', 'Use flexible question patterns', 'Clear instruction headings']
            },
            {
                'extension': '.html/.htm',
                'name': 'HTML Document',
                'description': 'Rich text support with flexible pattern matching and full instruction detection',
                'features': ['Full HTML formatting', 'Images', 'Mathematical symbols', 'Very flexible patterns', 'Advanced instruction parsing'],
                'requirements': ['Valid HTML structure', 'Flexible question patterns', 'Clear instruction markup']
            },
            {
                'extension': '.xlsx/.xls',
                'name': 'Excel Spreadsheet',
                'description': 'Structured format with separate instruction handling',
                'features': ['Batch processing', 'Separate sheets for MCQ/Theory', 'Dedicated instruction columns'],
                'mcq_format': {
                    'columns': ['Question', 'Option A', 'Option B', 'Option C', 'Option D', 'Correct Answer', 'Marks', 'Instructions'],
                    'example': ['What is 2+2?', '3', '4', '5', '6', 'B', '1', 'Choose the correct answer']
                },
                'theory_format': {
                    'columns': ['Question', 'Sub-questions', 'Marks', 'Instructions'],
                    'example': ['Explain photosynthesis', 'a) Define photosynthesis b) List factors', '10', 'Answer all parts clearly']
                }
            }
        ],
        'question_formatting_guide': {
            'overview': 'The system now supports VERY FLEXIBLE question formatting patterns. You can use various punctuation marks and spacing.',
            'question_patterns': {
                'numbered_questions': {
                    'description': 'Questions can start with numbers in many formats',
                    'examples': [
                        '1. What is the capital of France?',
                        '1) Which of the following is correct?',
                        '1, Define photosynthesis',
                        '1: Explain the water cycle',
                        '1- Choose the best answer',
                        '1 What is 2+2?',  # No punctuation
                        'Q1. What is photosynthesis?',
                        'Q1) Which is correct?',
                        'Q.1 Define the term',
                        'Question 1. Explain',
                        'Question.1) What is',
                        '(1) Choose the answer',
                        '(1). Which of these',
                        'No.1 What is',
                        'No 1. Define'
                    ]
                },
                'lettered_questions': {
                    'description': 'Questions can also start with letters for sections',
                    'examples': [
                        'A. What is the main idea?',
                        'A) Choose the correct option',
                        'A: Define the following',
                        'I. Explain photosynthesis',
                        'II) What is the process'
                    ]
                }
            },
            'option_patterns': {
                'description': 'MCQ options support many formats with flexible punctuation',
                'examples': [
                    # Letter-based options
                    'a. Paris',
                    'a) London', 
                    'a, Berlin',
                    'a: Rome',
                    'a- Madrid',
                    'a Tokyo',  # No punctuation
                    'A. Paris',
                    'A) London',
                    'A, Berlin', 
                    'A: Rome',
                    'A- Madrid',
                    'A Tokyo',  # No punctuation
                    '(a) Paris',
                    '(A) London',
                    '(a). Berlin',
                    
                    # Number-based options
                    '1. Paris',
                    '2) London',
                    '3, Berlin',
                    '4: Rome',
                    '(1) Paris',
                    '(2). London',
                    
                    # Roman numerals
                    'i. First option',
                    'ii) Second option',
                    'iii. Third option',
                    
                    # Bullet points
                    '- First option',
                    '• Second option',
                    '* Third option'
                ]
            },
            'correct_answer_marking': {
                'description': 'Mark correct answers using various indicators',
                'examples': [
                    'a) Paris *',
                    'b) London ✓',
                    'c) Berlin √',
                    'd) Rome (correct)',
                    'A) Paris [answer]',
                    'B) London (right)',
                    'C) Berlin [correct]',
                    'D) Rome ans',
                    'a. Paris (✓)',
                    'b. London [*]',
                    'c. Berlin (ans)',
                    'Option text (true)',
                    '<strong>Paris</strong>',  # Bold text
                    '<b>London</b>',  # Bold text
                    'PARIS',  # All caps might indicate correct
                ]
            },
            'marks_patterns': {
                'description': 'Specify marks using various formats',
                'examples': [
                    'Question text [5 marks]',
                    'Question text (10 points)',
                    'Question text [3 pts]',
                    'Question text 5 marks',
                    'Question text 2 points',
                    'Question text 1 pt',
                    'Question text - 5 marks',
                    'Question text — 3 points',
                    'Question text 5m',
                    'Question text 2p',
                    'Question text marks: 5',
                    'Question text points = 3',
                    'Question text total: 10'
                ]
            }
        },
        'instruction_guide': {
            'overview': 'Instructions are automatically detected and associated with questions. The system recognizes various instruction patterns and links them to the appropriate questions.',
            'supported_patterns': [
                {
                    'type': 'General Instructions',
                    'patterns': ['INSTRUCTIONS:', 'INSTRUCTION:', 'GENERAL INSTRUCTIONS:', 'DIRECTIONS:'],
                    'description': 'General instructions that apply to all questions',
                    'example': 'INSTRUCTIONS: Answer all questions. Each question carries equal marks.'
                },
                {
                    'type': 'Section Instructions',
                    'patterns': ['SECTION A:', 'SECTION B:', 'PART I:', 'PART II:', 'COMPONENT 1:', 'COMPONENT 2:'],
                    'description': 'Instructions specific to a section or part of the exam',
                    'example': 'SECTION A: MULTIPLE CHOICE QUESTIONS\nChoose the correct answer from the options provided.'
                },
                {
                    'type': 'Subject Component Instructions',
                    'patterns': ['SYNONYMS:', 'ANTONYMS:', 'GRAMMAR:', 'COMPREHENSION:', 'VOCABULARY:', 'LEXIS:', 'STRUCTURE:'],
                    'description': 'Instructions for specific subject components (especially useful for English)',
                    'example': 'SYNONYMS: Choose the word that means the same as the underlined word.'
                },
                {
                    'type': 'Question Range Instructions',
                    'patterns': ['Instructions for Questions 1-10:', 'For Questions 11-20:', 'Questions 1 to 5:'],
                    'description': 'Instructions that apply to a specific range of questions',
                    'example': 'Instructions for Questions 1-10: Choose the correct answer from the options below.'
                },
                {
                    'type': 'Component Descriptions',
                    'patterns': ['LEXIS AND STRUCTURE: Choose...', 'READING COMPREHENSION: Read...'],
                    'description': 'Combined component name and instruction in one line',
                    'example': 'LEXIS AND STRUCTURE: Choose the correct option to complete each sentence.'
                }
            ],
            'best_practices': [
                'Place instructions before the questions they apply to',
                'Use clear, descriptive headings in UPPERCASE or bold',
                'Keep instructions concise but comprehensive',
                'Use consistent formatting throughout the document',
                'For subject components (like English), clearly label each section',
                'Specify question ranges when instructions change',
                'Use standard instruction keywords for better detection'
            ],
            'formatting_examples': {
                'comprehensive_document': [
                    '📄 COMPLETE DOCUMENT EXAMPLE WITH FLEXIBLE FORMATTING:',
                    '',
                    'INSTRUCTIONS: Answer all questions clearly. Each carries marks as indicated.',
                    '',
                    'SECTION A: MULTIPLE CHOICE QUESTIONS',
                    'Choose the correct answer from the four options provided.',
                    '',
                    '1. What is the capital of France? [2 marks]',
                    'a) London',
                    'b) Paris ✓',
                    'c) Berlin', 
                    'd) Rome',
                    '',
                    '2) Which planet is closest to the sun? (1 point)',
                    'A. Venus',
                    'B, Mercury *',
                    'C: Earth',
                    'D- Mars',
                    '',
                    '3 What is 2+2? 1m',
                    'a. Three',
                    'b, Four (correct)',
                    'c: Five',
                    'd- Six',
                    '',
                    'SECTION B: SYNONYMS',
                    'Choose the word that means the same as the underlined word.',
                    '',
                    '4. The weather was quite pleasant.',
                    'a) harsh',
                    'b) nice [answer]',
                    'c) cold',
                    'd) wet',
                    '',
                    'SECTION C: THEORY QUESTIONS',
                    'Answer all parts of each question.',
                    '',
                    '5. Explain photosynthesis. [10 marks]',
                    'a) Define photosynthesis (3 marks)',
                    'b) List the factors affecting photosynthesis (4 marks)',
                    'c) Explain the importance of photosynthesis (3 marks)',
                    '',
                    '6) Describe the water cycle 8pts',
                    'i. Define evaporation 2pts',
                    'ii) Explain condensation 3pts', 
                    'iii. Describe precipitation 3pts'
                ],
                'mcq_variations': [
                    '📝 MCQ FORMATTING VARIATIONS:',
                    '',
                    '1. Standard format:',
                    'a) Option one',
                    'b) Option two ✓',
                    '',
                    '2) With commas:',
                    'A, First choice',
                    'B, Second choice *',
                    '',
                    '3: With colons:',
                    'a: Choice A',
                    'b: Choice B (correct)',
                    '',
                    '4- With dashes:',
                    'A- Option A',
                    'B- Option B [right]',
                    '',
                    '5 No punctuation after number:',
                    'a Option 1',
                    'b Option 2 ans',
                    '',
                    '(6) Parentheses:',
                    '(a) First',
                    '(b) Second ✓',
                    '',
                    'Q7. Question format:',
                    '1. Choice 1',
                    '2. Choice 2 (answer)',
                    '',
                    'Question 8) Another format:',
                    'i. Roman numeral option',
                    'ii. Roman numeral option √'
                ],
                'theory_variations': [
                    '📚 THEORY QUESTION VARIATIONS:',
                    '',
                    '1. With explicit sub-questions:',
                    'a) First part [3 marks]',
                    'b) Second part [4 marks]',
                    'c) Third part [3 marks]',
                    '',
                    '2) With roman numerals:',
                    'i. First sub-question 2pts',
                    'ii. Second sub-question 3pts',
                    'iii. Third sub-question 5pts',
                    '',
                    '3: Mixed numbering:',
                    '(a) Part one (2 marks)',
                    '(b) Part two (3 marks)',
                    '',
                    '4- Simple structure:',
                    'a. Define the term 4m',
                    'b. Give examples 6m',
                    '',
                    '5 No sub-questions (single answer):',
                    'Explain in detail... [10 marks]'
                ],
                'marks_variations': [
                    '🔢 MARKS FORMATTING VARIATIONS:',
                    '',
                    '[5 marks] - Standard brackets',
                    '(10 points) - Parentheses',
                    '[3 pts] - Abbreviated points',
                    '5 marks - No brackets',
                    '2 points - Simple format',
                    '1 pt - Short form',
                    '- 5 marks - With dash',
                    '— 3 points - With em dash',
                    '5m - Very short',
                    '2p - Minimal',
                    'marks: 5 - With colon',
                    'points = 3 - With equals',
                    'total: 10 - Total marks'
                ]
            },
            'instruction_association': {
                'automatic_linking': 'Instructions are automatically linked to questions based on their position and context',
                'scope_rules': [
                    'General instructions apply to all questions in the document',
                    'Section instructions apply to questions in that section until a new section begins',
                    'Component instructions apply to questions of that specific component',
                    'Range instructions apply only to the specified question numbers',
                    'Questions inherit the most specific instruction available'
                ],
                'override_behavior': 'More specific instructions override general ones (Range > Component > Section > General)'
            }
        },
        'troubleshooting_guide': {
            'common_issues': [
                {
                    'issue': 'Questions not being detected',
                    'solutions': [
                        'Ensure questions start with numbers (1., 1), 1:, etc.) or Q1:, Question 1',
                        'Make sure there\'s space or punctuation after the question number',
                        'Check that question text has at least 3 words',
                        'Try different number formats: 1., 1), 1:, 1-, or just 1 followed by text'
                    ]
                },
                {
                    'issue': 'Options not being recognized',
                    'solutions': [
                        'Start options with a., a), A., A), (a), (A), 1., 2., etc.',
                        'Use any punctuation: period, comma, colon, dash, or just space',
                        'Ensure each option has at least 2 words',
                        'Place options immediately after the question'
                    ]
                },
                {
                    'issue': 'Correct answers not detected',
                    'solutions': [
                        'Mark with: *, ✓, √, (correct), [answer], (right), ans',
                        'Use bold formatting for the correct option',
                        'Add indicators at the end of the option text',
                        'Try different symbols or words for marking'
                    ]
                },
                {
                    'issue': 'Marks not extracted',
                    'solutions': [
                        'Use formats like: [5 marks], (10 points), 5pts, 5m',
                        'Place marks at the end of question text',
                        'Try: marks: 5, points = 3, total: 10',
                        'Use reasonable numbers (1-100 for total, 1-20 for individual)'
                    ]
                },
                {
                    'issue': 'Instructions not detected',
                    'solutions': [
                        'Use clear headings: INSTRUCTIONS:, SECTION A:, SYNONYMS:',
                        'Place instructions before relevant questions',
                        'Use uppercase or bold formatting for instruction headings',
                        'Keep instructions descriptive and substantial (more than 3 words)'
                    ]
                }
            ],
            'validation_modes': [
                {
                    'mode': 'Strict Mode',
                    'description': 'Only accepts perfectly formatted questions',
                    'use_when': 'Your document is well-formatted and you want high quality'
                },
                {
                    'mode': 'Lenient Mode',
                    'description': 'Attempts to fix common issues automatically',
                    'use_when': 'Your document has formatting issues and you want maximum questions parsed',
                    'auto_fixes': [
                        'Adds missing correct option (defaults to first)',
                        'Ensures minimum 2 options for MCQ',
                        'Sets default marks to 1 if missing',
                        'Creates default sub-questions for theory questions',
                        'Fixes marks consistency between sub-questions'
                    ]
                }
            ]
        },
        'tips': [
            '💡 **FLEXIBILITY**: The parser now accepts many formatting variations - don\'t worry about perfect formatting!',
            '🔢 **Question Numbers**: Use any format: 1., 1), 1:, 1-, Q1, Question 1, or even just "1 What is..."',
            '📝 **Options**: Start with a/A, use any punctuation (., ), :, -, ,) or just space',
            '✅ **Correct Answers**: Mark with *, ✓, (correct), [answer], (right), ans, or make it bold',
            '⚖️ **Marks**: Use [5 marks], (10 points), 5pts, 5m, or just 5 anywhere in the question',
            '📋 **Instructions**: Use clear headings like INSTRUCTIONS:, SECTION A:, SYNONYMS:',
            '🔄 **Use Lenient Mode**: If strict mode parses too few questions, try lenient mode for auto-fixes',
            '📄 **Test Small First**: Upload a small document first to verify your formatting works',
            '🎯 **Be Consistent**: While flexible, consistent formatting throughout gives best results',
            '🔍 **Review Preview**: Always check the preview before confirming import',
            '📚 **Theory Questions**: Can have sub-questions (a, b, c) or be single-answer questions',
            '🏷️ **Subject Components**: For English exams, clearly separate SYNONYMS, GRAMMAR, etc. sections'
        ],
        'limitations': [
            'Maximum file size: 50MB',
            'Complex layouts in PDF may not parse correctly',
            'Images in PDF are not extracted',
            'Very large documents may take time to process',
            'Instruction detection works best with clear, standard formatting',
            'Nested or complex instruction hierarchies may not be fully supported'
        ]
    }
    
    return jsonify(format_info), 200


@bp.route('/admin/bulk-upload/template/<format_type>', methods=['GET'])
@admin_required
def download_template(format_type):
    """Download template files for different formats."""
    
    if format_type not in ['mcq_excel', 'theory_excel', 'mixed_excel', 'word_sample']:
        return jsonify({'error': 'Invalid template type'}), 400
    
    # In a real implementation, you would generate and return actual template files
    # For now, return template structure information
    
    templates = {
        'mcq_excel': {
            'description': 'Excel template for MCQ questions',
            'headers': ['Question', 'Option A', 'Option B', 'Option C', 'Option D', 'Correct Answer', 'Marks'],
            'sample_row': ['What is the capital of France?', 'London', 'Paris', 'Berlin', 'Rome', 'B', '1'],
            'instructions': [
                'Put each question in a separate row',
                'Use column F for correct answer (A, B, C, or D)',
                'Specify marks in the last column',
                'You can add more option columns if needed'
            ]
        },
        'theory_excel': {
            'description': 'Excel template for Theory questions',
            'headers': ['Question', 'Sub-questions', 'Marks', 'Instructions'],
            'sample_row': ['Explain the water cycle', 'a) Define evaporation b) Describe condensation c) Explain precipitation', '15'],
            'instructions': [
                'Main question in first column',
                'Sub-questions in second column (use a), b), c) format)',
                'Total marks for the entire question in third column',
                'For questions without sub-parts, leave sub-questions column empty'
            ]
        },
        'mixed_excel': {
            'description': 'Excel template with separate sheets for MCQ and Theory',
            'sheets': {
                'MCQ Questions': 'Sheet for multiple choice questions',
                'Theory Questions': 'Sheet for theory/essay questions'
            },
            'instructions': [
                'Use separate sheets for different question types',
                'Name sheets clearly (e.g., "MCQ", "Theory", "Multiple Choice")',
                'Follow the respective formats for each sheet type'
            ]
        },
        'word_sample': {
            'description': 'Sample Word document structure',
            'structure': [
                '1. What is photosynthesis? [2 marks]',
                'a) The process of making food',
                'b) The process of breathing',
                'c) The process of growing *',
                'd) The process of reproduction',
                '',
                '2. Explain the importance of forests. [10 marks]',
                'a) Discuss the ecological benefits (5 marks)',
                'b) Explain economic importance (5 marks)',
                '',
                '3. Choose the correct answer: What is 2+2?',
                'A) 3',
                'B) 4 ✓',
                'C) 5',
                'D) 6'
            ],
            'formatting_tips': [
                'Use bold for question numbers',
                'Mark correct answers with *, ✓, or (correct)',
                'Include marks in brackets like [5 marks]',
                'Use consistent numbering and lettering',
                'Separate questions with blank lines'
            ]
        }
    }
    
    return jsonify(templates[format_type]), 200 