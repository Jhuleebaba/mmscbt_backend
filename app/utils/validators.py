import re


def validate_required_fields(data, required_fields):
    """
    Validate that required fields are present in data.
    Returns tuple (is_valid, missing_fields)
    """
    missing = []
    for field in required_fields:
        if field not in data or data[field] is None or data[field] == '':
            missing.append(field)
    
    return len(missing) == 0, missing


def sanitize_string(value, max_length=None):
    """
    Sanitize a string value by stripping whitespace
    and optionally truncating to max_length.
    """
    if not isinstance(value, str):
        return value
    
    value = value.strip()
    
    if max_length and len(value) > max_length:
        value = value[:max_length]
    
    return value


def validate_admission_number(admission_number):
    """
    Validate admission number format.
    Returns tuple (is_valid, error_message)
    """
    if not admission_number:
        return False, "Admission number is required"
    
    admission_number = admission_number.strip()
    
    if len(admission_number) < 3:
        return False, "Admission number is too short"
    
    if len(admission_number) > 50:
        return False, "Admission number is too long"
    
    return True, None


def validate_question_data(question_data):
    """
    Validate question data for exam questions.
    Returns tuple (is_valid, error_message)
    """
    required_fields = ['question_text', 'question_type', 'marks']
    is_valid, missing = validate_required_fields(question_data, required_fields)
    
    if not is_valid:
        return False, f"Missing required fields: {', '.join(missing)}"
    
    question_type = question_data.get('question_type')
    
    if question_type not in ['mcq', 'theory']:
        return False, "Invalid question type. Must be 'mcq' or 'theory'"
    
    if question_type == 'mcq':
        options = question_data.get('options', [])
        if not options or len(options) < 2:
            return False, "MCQ questions must have at least 2 options"
        
        correct_option = question_data.get('correct_option')
        if correct_option is None:
            return False, "MCQ questions must have a correct option specified"
        
        if not isinstance(correct_option, int) or correct_option < 0 or correct_option >= len(options):
            return False, "Invalid correct option index"
    
    marks = question_data.get('marks')
    if not isinstance(marks, (int, float)) or marks <= 0:
        return False, "Marks must be a positive number"
    
    return True, None
