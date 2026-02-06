from datetime import datetime
import re
from app import mongo
from app.models.academic import Class

def get_class_type(class_id):
    """
    Determine if a class is JS (Junior Secondary) or SS (Senior Secondary)
    Returns: 'JS', 'SS', or None if undetermined
    """
    class_obj = Class.find_by_id(class_id)
    if not class_obj:
        return None
    
    # Check class name or level to determine type
    class_name = class_obj.get('name', '').upper()
    level = class_obj.get('level', 0)
    
    # Try to determine from name first
    if 'JSS' in class_name or 'JUNIOR' in class_name:
        return 'JS'
    if 'SSS' in class_name or 'SENIOR' in class_name:
        return 'SS'
    
    # Fallback to level/logic if specific naming convention is used
    # Assuming JSS 1-3 correspond to levels ?? (Need to be flexible)
    # Defaulting to JS/SS based on typical patterns if name is ambiguous
    # If standard naming 'JSS 1', 'SSS 2' is used, the above covers it.
    
    # If unmatchable, default to JS? Or maybe we should enforce naming?
    # Let's try flexible regex for just 'J' or 'S' at start
    if class_name.startswith('J'):
        return 'JS'
    if class_name.startswith('S'):
        return 'SS'
        
    return 'JS' # Default fallback if nothing matches, to avoid failure

def generate_admission_number(class_id):
    """
    Generate the next available admission number in format MMC/YY(JS/SS)/XXX
    Implements smart gap filling.
    """
    # 1. Determine YY (Year)
    current_year = datetime.now().year
    yy = str(current_year)[-2:] # Last 2 digits, e.g., '25'
    
    # 2. Determine JS/SS
    class_type = get_class_type(class_id)
    if not class_type:
        # If class not found, perform fallback?
        class_type = 'JS' 
        
    prefix = f"MMC/{yy}{class_type}/" # e.g., MMC/25JS/
    
    # 3. Smart Gap Filling
    # Find all student admission numbers that start with this prefix
    # RegEx for MongoDB: ^MMC/25JS/\d{3}$
    regex_pattern = f"^{re.escape(prefix)}\\d{{3}}$"
    
    pipeline = [
        {
            "$match": {
                "user_type": "student",
                "admission_number": {"$regex": regex_pattern}
            }
        },
        {
            "$project": {
                "admission_number": 1
            }
        }
    ]
    
    existing_students = list(mongo.db.users.aggregate(pipeline))
    
    # Extract existing numbers
    existing_numbers = set()
    for student in existing_students:
        adm_no = student.get('admission_number', '')
        try:
            # MMC/25JS/012 -> 012 -> 12
            number_part = int(adm_no.split('/')[-1])
            existing_numbers.add(number_part)
        except (ValueError, IndexError):
            continue
            
    # Find first missing number starting from 1
    next_number = 1
    while next_number in existing_numbers:
        next_number += 1
        
    # Format: 001, 012, 123
    return f"{prefix}{next_number:03d}"
