"""
SNAPSHOT-BASED QUESTION PARSER
================================

Ultra-flexible parsing approach:
- Identify question numbers and option letters
- Capture EVERYTHING in between as content (text, images, formatting)
- Detect correct answer markers anywhere in option content
- Maximum flexibility and convenience

This parser treats content as "snapshots" - whatever appears between
structural markers (question numbers, option letters) is captured as-is.
"""

import re
import base64
import logging
from typing import List, Dict, Any, Optional, Tuple
import docx
from io import BytesIO

logger = logging.getLogger(__name__)


class SnapshotParser:
    """
    Snapshot-based parser that captures content blocks between structural markers.
    
    Philosophy:
    - Question number = Start of question block
    - Option letter = Start of option block
    - Everything between = Content (text, images, formatting)
    - Correct markers = Identify correct option
    """
    
    def __init__(self):
        # Question number patterns (very flexible)
        self.question_patterns = [
            r'^\s*(\d+)[\.\)\:\-\s]',           # 1. or 1) or 1: or 1-
            r'^\s*Q\.?\s*(\d+)[\.\)\:\-\s]*',   # Q1 or Q.1
            r'^\s*Question\s*\.?\s*(\d+)',      # Question 1
            r'^\s*\((\d+)\)',                   # (1)
            r'^\s*No\.?\s*(\d+)',               # No.1
        ]
        
        # Option letter patterns (very flexible) - anchor at start, avoid matching inside text
        self.option_patterns = [
            r'^\s*([A-Ha-h])[\.\)\:\-\s]',      # A. or A) or A: (extended to H)
            r'^\s*\(([A-Ha-h])\)',              # (A)
            r'^\s*([A-Ha-h])\s+',               # A followed by space
        ]
        
        # Correct answer markers (very flexible)
        self.correct_markers = [
            r'\(correct\)',                      # (correct)
            r'\[correct\]',                      # [correct]
            r'\*correct\*',                      # *correct*
            r'\bcorrect\b',                      # correct (word boundary)
            r'✓',                                # Checkmark
            r'✔',                                # Heavy checkmark
            r'→',                                # Arrow
            r'\(answer\)',                       # (answer)
            r'\[answer\]',                       # [answer]
        ]
    
    def parse_docx_snapshot(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Parse DOCX using snapshot approach.
        
        Process:
        1. Scan document for question numbers and option letters
        2. Capture all content between markers (text + images)
        3. Detect correct answer markers
        4. Build questions with captured content
        """
        try:
            import tempfile
            import os
            
            # Create temp file
            temp_fd, temp_file = tempfile.mkstemp(suffix='.docx')
            
            try:
                with os.fdopen(temp_fd, 'wb') as f:
                    f.write(file_content)
                
                # Open document (use factory, not Document class)
                doc = docx.Document(temp_file)
                
                # Extract all images first
                image_map = self._extract_all_images(doc)
                
                # Parse using snapshot method
                questions = self._parse_snapshot_structure(doc, image_map)
                
                return {
                    'mcq_questions': questions,
                    'theory_questions': [],
                    'total_questions': len(questions),
                    'format': 'docx_snapshot',
                    'warnings': []
                }
                
            finally:
                if os.path.exists(temp_file):
                    try:
                        os.unlink(temp_file)
                    except:
                        pass
                        
        except Exception as e:
            logger.error(f"Error in snapshot parsing: {str(e)}")
            raise
    
    def _extract_all_images(self, doc) -> Dict[str, str]:
        """Extract all images and map by relationship ID."""
        image_map = {}
        
        try:
            for rel in doc.part.rels.values():
                if "image" in rel.target_ref:
                    try:
                        image_part = rel.target_part
                        image_bytes = image_part.blob
                        content_type = image_part.content_type
                        
                        # Convert to base64
                        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
                        image_data = f"data:{content_type};base64,{image_base64}"
                        
                        image_map[rel.rId] = image_data
                        
                    except Exception as e:
                        logger.warning(f"Failed to extract image {rel.rId}: {str(e)}")
                        
        except Exception as e:
            logger.warning(f"Error extracting images: {str(e)}")
        
        logger.info(f"Extracted {len(image_map)} images from document")
        return image_map
    
    def _parse_snapshot_structure(self, doc, image_map: Dict[str, str]) -> List[Dict]:
        """
        Parse document structure using snapshot approach.
        
        Algorithm:
        1. Scan paragraphs sequentially
        2. When question number found → Start new question
        3. When option letter found → Start new option
        4. Capture everything in between (text + images)
        5. Detect correct markers
        """
        questions = []
        current_question = None
        current_option_index = None
        current_content = []
        
        for para_idx, paragraph in enumerate(doc.paragraphs):
            text = paragraph.text.strip()
            
            if not text:
                continue
            
            # Check if this is a question number
            question_match = self._detect_question_number(text)
            
            if question_match:
                # Save previous question if exists
                if current_question:
                    self._finalize_question(current_question, current_content, current_option_index)
                    questions.append(current_question)
                
                # Start new question
                question_number = question_match['number']
                question_text_start = question_match['text_after']
                
                current_question = {
                    'question_number': question_number,
                    'question_text': '',
                    'question_image': None,
                    'options': [],
                    'option_images': [],
                    'correct_option': 0,
                    'marks': 1,
                    'content_type': 'text',
                    'has_rich_content': False
                }
                
                current_content = []
                current_option_index = None
                
                # Capture content and images from this paragraph
                content_data = self._capture_paragraph_content(paragraph, image_map, question_text_start)
                current_content.append(content_data)
                
                logger.debug(f"Started question {question_number}")
                continue
            
            # Check if this is an option letter
            if current_question:
                option_match = self._detect_option_letter(text)
                
                if option_match:
                    # Save previous option content if exists
                    if current_option_index is not None:
                        self._finalize_option(current_question, current_content, current_option_index)
                    else:
                        # This was question content, finalize it
                        self._finalize_question_content(current_question, current_content)
                    
                    # Start new option
                    option_letter = option_match['letter']
                    option_text_start = option_match['text_after']
                    current_option_index = ord(option_letter.upper()) - ord('A')
                    
                    current_content = []
                    
                    # Capture content from this paragraph
                    content_data = self._capture_paragraph_content(paragraph, image_map, option_text_start)
                    current_content.append(content_data)
                    
                    # Check if this option is marked as correct
                    if self._is_marked_correct(text) or self._is_marked_correct(option_text_start):
                        current_question['correct_option'] = current_option_index
                        logger.debug(f"Option {option_letter} marked as correct")
                    
                    logger.debug(f"Started option {option_letter}")
                    continue
            
            # This is continuation content (for question or option)
            if current_question:
                content_data = self._capture_paragraph_content(paragraph, image_map)
                current_content.append(content_data)
        
        # Save last question
        if current_question:
            if current_option_index is not None:
                self._finalize_option(current_question, current_content, current_option_index)
            else:
                self._finalize_question_content(current_question, current_content)
            questions.append(current_question)
        
        logger.info(f"Parsed {len(questions)} questions using snapshot method")
        return questions
    
    def _detect_question_number(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect if text starts with a question number."""
        for pattern in self.question_patterns:
            match = re.match(pattern, text, re.IGNORECASE)
            if match:
                number = int(match.group(1))
                text_after = text[match.end():].strip()
                return {
                    'number': number,
                    'text_after': text_after
                }
        return None
    
    def _detect_option_letter(self, text: str) -> Optional[Dict[str, Any]]:
        """Detect if text starts with an option letter."""
        for pattern in self.option_patterns:
            match = re.match(pattern, text, re.IGNORECASE)
            if match:
                letter = match.group(1).upper()
                text_after = text[match.end():].strip()
                return {
                    'letter': letter,
                    'text_after': text_after
                }
        return None
    
    def _is_marked_correct(self, text: str) -> bool:
        """Check if text contains correct answer markers."""
        text_lower = text.lower()
        for marker in self.correct_markers:
            if re.search(marker, text_lower, re.IGNORECASE):
                return True
        return False
    
    def _capture_paragraph_content(self, paragraph, image_map: Dict[str, str], 
                                   initial_text: str = None) -> Dict[str, Any]:
        """
        Capture all content from a paragraph (text + images + formatting).
        
        Returns a content block with:
        - text: HTML-formatted text
        - images: List of image data
        """
        content = {
            'text': initial_text or '',
            'images': []
        }
        
        # Build HTML from runs (preserves formatting). If initial_text is provided,
        # we avoid appending run text again to prevent duplicated content because
        # initial_text already contains the paragraph text after the marker.
        html_parts = []
        
        for run in paragraph.runs:
            run_text = run.text
            
            # Apply formatting
            if run.bold:
                run_text = f'<strong>{run_text}</strong>'
            if run.italic:
                run_text = f'<em>{run_text}</em>'
            if run.underline:
                run_text = f'<u>{run_text}</u>'
            
            # Handle superscript/subscript
            if hasattr(run.font, 'superscript') and run.font.superscript:
                run_text = f'<sup>{run_text}</sup>'
            if hasattr(run.font, 'subscript') and run.font.subscript:
                run_text = f'<sub>{run_text}</sub>'
            
            if initial_text is None:
                html_parts.append(run_text)
            
            # Check for images in this run
            if hasattr(run, '_element'):
                drawings = run._element.findall(
                    './/{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing'
                )
                
                for drawing in drawings:
                    blips = drawing.findall(
                        './/{http://schemas.openxmlformats.org/drawingml/2006/main}blip'
                    )
                    
                    for blip in blips:
                        rId = blip.get(
                            '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed'
                        )
                        
                        if rId and rId in image_map:
                            content['images'].append(image_map[rId])
        
        # Combine HTML parts
        if initial_text is None and html_parts:
            combined_html = ''.join(html_parts)
            if content['text']:
                content['text'] += ' ' + combined_html
            else:
                content['text'] = combined_html
        
        return content
    
    def _finalize_question_content(self, question: Dict, content_blocks: List[Dict]):
        """Finalize question content from captured blocks."""
        # Combine all text
        text_parts = [block['text'] for block in content_blocks if block['text']]
        combined = '<br>'.join(text_parts).strip()
        question['question_text'] = self._normalize_math_html(combined)
        
        # Collect all images
        all_images = []
        for block in content_blocks:
            all_images.extend(block['images'])
        
        # Set primary question image
        if all_images:
            question['question_image'] = all_images[0]
            question['has_rich_content'] = True
            question['content_type'] = 'mixed' if question['question_text'] else 'image'
    
    def _finalize_option(self, question: Dict, content_blocks: List[Dict], option_index: int):
        """Finalize option content from captured blocks."""
        # Combine all text
        text_parts = [block['text'] for block in content_blocks if block['text']]
        option_text = '<br>'.join(text_parts).strip()
        option_text = self._normalize_math_html(option_text)
        
        # Remove correct markers from display text
        for marker in self.correct_markers:
            option_text = re.sub(marker, '', option_text, flags=re.IGNORECASE)
        option_text = option_text.strip()
        
        # Collect all images
        all_images = []
        for block in content_blocks:
            all_images.extend(block['images'])
        
        # Ensure options list is large enough
        while len(question['options']) <= option_index:
            question['options'].append('')
            question['option_images'].append(None)
        
        # Set option content
        question['options'][option_index] = option_text
        
        # Set option image if exists
        if all_images:
            question['option_images'][option_index] = all_images[0]
            question['has_rich_content'] = True
            question['content_type'] = 'mixed'
    
    def _finalize_question(self, question: Dict, content_blocks: List[Dict], 
                          last_option_index: Optional[int]):
        """Finalize the last option or question content."""
        if last_option_index is not None:
            self._finalize_option(question, content_blocks, last_option_index)
        else:
            self._finalize_question_content(question, content_blocks)
        # Normalize to remove empty/duplicate options and fix correct index
        self._normalize_final_question(question)

    def _normalize_math_html(self, html: str) -> str:
        """Normalize math-like constructs: stacked fractions and caret exponents."""
        import re
        if not html:
            return html
        out = html
        # 1) Convert caret exponents: x^2 -> x<sup>2</sup> (avoid if already inside <sup>)
        # Simple heuristic: replace ^word following an alnum
        def repl_caret(m):
            base = m.group(1)
            exp = m.group(2)
            return f"{base}<sup>{exp}</sup>"
        out = re.sub(r'([A-Za-z0-9\)\]])\^([A-Za-z0-9]+)', repl_caret, out)

        # Convert ^o into degrees symbol when following a number (e.g., 90^o -> 90°)
        out = re.sub(r'([0-9])\^o\b', r'\1°', out, flags=re.IGNORECASE)

        # 2) Detect stacked fraction patterns across <br> boundaries.
        # Patterns: (number)(<br>line)?<br>(number) => render as fraction
        # Accept an optional middle line composed of dashes/underscores/boxes
        def fraction_replacer(match):
            num = match.group(1)
            den = match.group(3)
            return f"<span class=\"fraction\"><span class=\"num\">{num}</span><span class=\"slash\">/</span><span class=\"den\">{den}</span></span>"

        # Case with a middle line
        out = re.sub(r'(?:^|<br>)(\d{1,4})(?:<br>[\-\–\—\_\=\u2500-\u257F\s]{1,50})<br>(\d{1,4})(?=(?:<br>|$))',
                     lambda m: fraction_replacer((None, m.group(1), None, m.group(2))), out)
        # Case without a middle line: two stacked numerals
        out = re.sub(r'(?:^|<br>)(\d{1,4})<br>(\d{1,4})(?=(?:<br>|$))',
                     lambda m: fraction_replacer((None, m.group(1), None, m.group(2))), out)

        return out

    def _normalize_final_question(self, question: Dict):
        """Remove empty/duplicate options and adjust correct_option index accordingly."""
        options = question.get('options', [])
        option_images = question.get('option_images', []) or []
        if not options:
            return
        # Ensure images array matches length
        while len(option_images) < len(options):
            option_images.append(None)

        def strip_html(s: str) -> str:
            import re
            base = re.sub(r'<[^>]*>', '', s or '').strip()
            # remove known correct markers to dedupe properly
            markers = [r'\(correct\)', r'\[correct\]', r'\*correct\*', r'✓', r'✔', r'→', r'\(answer\)', r'\[answer\]']
            for m in markers:
                base = re.sub(m, '', base, flags=re.IGNORECASE).strip()
            return base

        seen = {}
        new_options = []
        new_images = []
        old_index_to_new = {}
        for idx, opt in enumerate(options):
            text_clean = strip_html(opt)
            if not text_clean:
                continue
            key = text_clean.lower()
            if key in seen:
                continue
            seen[key] = len(new_options)
            old_index_to_new[idx] = len(new_options)
            new_options.append(opt)
            new_images.append(option_images[idx] if idx < len(option_images) else None)

        # If we removed everything, keep original to let validator handle
        if not new_options:
            return

        # Remap correct option if possible
        old_correct = question.get('correct_option', 0) or 0
        if old_correct in old_index_to_new:
            question['correct_option'] = old_index_to_new[old_correct]
        else:
            # Try to map by text equality
            try:
                old_text = strip_html(options[old_correct]) if old_correct < len(options) else ''
                if old_text:
                    mapped = seen.get(old_text.lower())
                    if mapped is not None:
                        question['correct_option'] = mapped
                    else:
                        question['correct_option'] = 0
                else:
                    question['correct_option'] = 0
            except Exception:
                question['correct_option'] = 0

        question['options'] = new_options
        question['option_images'] = new_images
def enable_snapshot_parsing():
    """
    Enable snapshot-based parsing for maximum flexibility.
    
    Usage:
        from app.utils.snapshot_parser import enable_snapshot_parsing
        enable_snapshot_parsing()
    """
    from app.utils.document_parser import DocumentParser
    
    snapshot_parser = SnapshotParser()
    
    # Monkey-patch the parse_document method
    original_parse = DocumentParser.parse_document
    
    def enhanced_parse(self, file_content: bytes, filename: str, question_type: str = 'auto'):
        """Enhanced parser with snapshot fallback."""
        try:
            # Try snapshot parsing for DOCX
            if filename.lower().endswith('.docx'):
                logger.debug("Using snapshot-based parsing for maximum flexibility")
                return snapshot_parser.parse_docx_snapshot(file_content, filename)
            else:
                # Use original parser for other formats
                return original_parse(self, file_content, filename, question_type)
        except Exception as e:
            logger.warning(f"Snapshot parsing failed, falling back to original: {str(e)}")
            return original_parse(self, file_content, filename, question_type)
    
    DocumentParser.parse_document = enhanced_parse
    
    logger.debug("Snapshot-based parsing enabled")


if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║  SNAPSHOT-BASED PARSER - ULTRA FLEXIBLE                      ║
    ╚══════════════════════════════════════════════════════════════╝
    
    HOW IT WORKS:
    ────────────────────────────────────────────────────
    1. Identifies question numbers (1., Q1, Question 1, etc.)
    2. Captures EVERYTHING after question number as content
    3. Identifies option letters (A., B., C., D., etc.)
    4. Captures EVERYTHING after option letter as content
    5. Detects correct markers: (correct), [correct], ✓, etc.
    
    EXAMPLE:
    ────────────────────────────────────────────────────
    1. What is this structure?
    [IMAGE: Benzene ring]
    Some additional text with **bold** formatting
    
    A. Benzene (correct)
    B. Cyclohexane
    C. Toluene
    D. Phenol
    
    RESULT:
    ────────────────────────────────────────────────────
    Question 1:
      - Text: "What is this structure? Some additional text..."
      - Image: [Benzene ring image]
      - Formatting: Preserved
      - Correct: Option A
    
    BENEFITS:
    ────────────────────────────────────────────────────
    ✅ Maximum flexibility
    ✅ No complex text parsing
    ✅ Handles ANY content type
    ✅ Works with screenshots
    ✅ Preserves all formatting
    ✅ Detects correct answers automatically
    """)
