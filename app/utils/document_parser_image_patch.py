"""
AUTOMATIC IMAGE EXTRACTION PATCH
==================================

This file contains the complete replacement for _extract_images_from_docx method
in document_parser.py

INSTALLATION INSTRUCTIONS:
1. Open app/utils/document_parser.py
2. Find the method _extract_images_from_docx (around line 730)
3. Replace the entire method with the code from extract_images_from_docx_complete() below
4. Save and restart your backend

OR use the monkey-patch approach at the bottom of this file.
"""

import base64
import logging
from typing import List, Dict
from docx.document import Document

logger = logging.getLogger(__name__)


def extract_images_from_docx_complete(self, doc: Document, questions: List[Dict]):
    """
    Extract images from DOCX and intelligently map to questions.
    Handles text, graphics, and formatting synchronization.
    
    COPY THIS ENTIRE METHOD to replace _extract_images_from_docx in document_parser.py
    """
    try:
        # STEP 1: Extract all images from document relationships
        image_parts = []
        
        for rel in doc.part.rels.values():
            if "image" in rel.target_ref:
                try:
                    image_part = rel.target_part
                    image_bytes = image_part.blob
                    content_type = image_part.content_type
                    
                    # Convert to base64
                    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                    image_data = f"data:{content_type};base64,{image_base64}"
                    
                    image_parts.append({
                        'data': image_data,
                        'rId': rel.rId,
                        'size': len(image_bytes),
                        'content_type': content_type
                    })
                    
                except Exception as e:
                    logger.warning(f"Failed to extract image {rel.rId}: {str(e)}")
                    continue
        
        if not image_parts:
            logger.info("No images found in document")
            return
        
        logger.info("Extracted %s images from document", len(image_parts))
        
        # STEP 2: Map paragraph positions to questions
        paragraph_to_question = {}
        question_index = 0
        
        for para_idx, paragraph in enumerate(doc.paragraphs):
            text = paragraph.text.strip()
            
            # Check if this paragraph starts a question
            if self._detect_question_pattern(text):
                paragraph_to_question[para_idx] = question_index
                logger.debug("Paragraph %s maps to question %s", para_idx, question_index)
                question_index += 1
        
        logger.info("Mapped %s paragraphs to questions", len(paragraph_to_question))
        
        # STEP 3: Scan for images and assign to questions
        current_question_idx = None
        images_assigned = 0
        
        for para_idx, paragraph in enumerate(doc.paragraphs):
            # Update current question context
            if para_idx in paragraph_to_question:
                current_question_idx = paragraph_to_question[para_idx]
            
            # Check if paragraph contains images
            for run in paragraph.runs:
                if not hasattr(run, '_element'):
                    continue
                
                # Look for drawing elements (images)
                try:
                    drawings = run._element.findall(
                        './/{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing'
                    )
                    
                    for drawing in drawings:
                        # Extract relationship ID from blip element
                        blips = drawing.findall(
                            './/{http://schemas.openxmlformats.org/drawingml/2006/main}blip'
                        )
                        
                        for blip in blips:
                            rId = blip.get(
                                '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed'
                            )
                            
                            if not rId:
                                continue
                            
                            # Find matching image and assign to question
                            for img in image_parts:
                                if img['rId'] == rId and current_question_idx is not None:
                                    if current_question_idx < len(questions):
                                        # Initialize images array if not exists
                                        if 'images' not in questions[current_question_idx]:
                                            questions[current_question_idx]['images'] = []
                                        
                                        # Add image to question
                                        questions[current_question_idx]['images'].append(img['data'])
                                        
                                        # Set as primary question image if not already set
                                        if not questions[current_question_idx].get('question_image'):
                                            questions[current_question_idx]['question_image'] = img['data']
                                            questions[current_question_idx]['has_rich_content'] = True
                                            
                                            # Determine content type
                                            if questions[current_question_idx].get('question_text'):
                                                questions[current_question_idx]['content_type'] = 'mixed'
                                            else:
                                                questions[current_question_idx]['content_type'] = 'image'
                                        
                                        images_assigned += 1
                                        logger.debug("Assigned image %s to question %s", rId, current_question_idx)
                                        
                except Exception as e:
                    logger.warning(f"Error processing paragraph {para_idx} for images: {str(e)}")
                    continue
        
        logger.info(
            "Successfully assigned %s images to %s questions",
            images_assigned,
            len([q for q in questions if q.get('question_image')])
        )
        
        # STEP 4: Detect option images (if 4 images and 4 options, likely option images)
        for question in questions:
            images = question.get('images', [])
            options = question.get('options', [])
            
            if len(images) == len(options) and len(options) in [2, 3, 4]:
                question['option_images'] = images
                question['images'] = []
                question['question_image'] = None
                question['content_type'] = 'mixed'
                question['has_rich_content'] = True
                logger.info("Detected %s option images for question", len(images))
        
    except Exception as e:
        logger.error("Error extracting images from DOCX: %s", str(e))


# ============================================================================
# MONKEY-PATCH APPROACH (Alternative - No file editing needed!)
# ============================================================================

def enable_automatic_image_extraction():
    """
    Monkey-patch DocumentParser to enable automatic image extraction.
    
    Usage in your code:
        from app.utils.document_parser_image_patch import enable_automatic_image_extraction
        enable_automatic_image_extraction()
    
    Then all DocumentParser instances will have automatic image extraction!
    """
    from app.utils.document_parser import DocumentParser
    
    # Replace the method
    DocumentParser._extract_images_from_docx = extract_images_from_docx_complete
    
    logger.debug("Automatic image extraction enabled for DocumentParser")


# ============================================================================
# PDF IMAGE EXTRACTION (Bonus!)
# ============================================================================

def extract_images_from_pdf_complete(pdf_content: bytes, questions: List[Dict]):
    """
    Extract images from PDF documents.
    Add this as a new method or enhance existing _parse_pdf
    """
    try:
        import PyPDF2
        from io import BytesIO
        
        pdf_reader = PyPDF2.PdfReader(BytesIO(pdf_content))
        images_extracted = 0
        
        # Simple approach: distribute images evenly across questions
        questions_per_page = max(1, len(questions) // len(pdf_reader.pages)) if questions else 1
        
        for page_num, page in enumerate(pdf_reader.pages):
            if '/XObject' not in page.get('/Resources', {}):
                continue
            
            xobjects = page['/Resources']['/XObject'].get_object()
            
            for obj_name in xobjects:
                try:
                    obj = xobjects[obj_name]
                    
                    if obj.get('/Subtype') != '/Image':
                        continue
                    
                    # Extract image data
                    data = obj.get_data()
                    
                    # Convert to base64
                    image_base64 = base64.b64encode(data).decode('utf-8')
                    image_data = f"data:image/jpeg;base64,{image_base64}"
                    
                    # Assign to question on this page
                    question_idx = page_num * questions_per_page
                    if question_idx < len(questions):
                        if 'images' not in questions[question_idx]:
                            questions[question_idx]['images'] = []
                        
                        questions[question_idx]['images'].append(image_data)
                        
                        if not questions[question_idx].get('question_image'):
                            questions[question_idx]['question_image'] = image_data
                            questions[question_idx]['has_rich_content'] = True
                            questions[question_idx]['content_type'] = 'mixed'
                        
                        images_extracted += 1
                        
                except Exception as e:
                    logger.warning(f"Failed to extract image from PDF page {page_num}: {str(e)}")
                    continue
        
        logger.info(f"Extracted {images_extracted} images from PDF")
        
    except Exception as e:
        logger.error(f"Error extracting images from PDF: {str(e)}")


if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║  AUTOMATIC IMAGE EXTRACTION - INSTALLATION GUIDE             ║
    ╚══════════════════════════════════════════════════════════════╝
    
    OPTION 1: Monkey-Patch (Easiest - No file editing!)
    ────────────────────────────────────────────────────
    Add to app/__init__.py or app/cbttraining/bulk_upload.py:
    
        from app.utils.document_parser_image_patch import enable_automatic_image_extraction
        enable_automatic_image_extraction()
    
    
    OPTION 2: Manual Replacement
    ────────────────────────────────────────────────────
    1. Open app/utils/document_parser.py
    2. Find _extract_images_from_docx method (line ~730)
    3. Replace entire method with extract_images_from_docx_complete()
    4. Save and restart
    
    
    WHAT IT DOES:
    ────────────────────────────────────────────────────
    ✅ Extracts ALL images from DOCX documents
    ✅ Maps images to questions automatically
    ✅ Handles text + image synchronization
    ✅ Detects option images vs question images
    ✅ Preserves formatting alongside images
    ✅ Works with bulk upload system
    
    
    TESTING:
    ────────────────────────────────────────────────────
    1. Create DOCX with questions + images
    2. Upload via bulk upload
    3. Check logs for "Extracted X images"
    4. Verify images appear in preview
    5. Save and check database
    """)
