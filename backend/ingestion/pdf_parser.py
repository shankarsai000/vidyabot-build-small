"""
PDF Parser Module

Extracts structured text from PDFs with chapter/section detection.
Uses pdfplumber for layout-aware text extraction.
Handles multi-column layouts common in Indian textbooks.
"""

import pdfplumber
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import re


@dataclass
class ParsedPage:
    """Structured representation of extracted text from a PDF page."""
    page_num: int
    chapter_num: Optional[int] = None
    chapter_title: Optional[str] = None
    section_title: Optional[str] = None
    raw_text: str = ""


class PDFParser:
    """Parses PDF textbooks and extracts structured content."""
    
    # Font size hresholds for heading detection (approximate, in points)
    CHAPTER_HEADING_MIN_SIZE = 18  # Large font = chapter heading
    SECTION_HEADING_MIN_SIZE = 14  # Medium font = section heading
    BODY_TEXT_SIZE = 10  # Normal text
    
    def __init__(self, pdf_path: str):
        """
        Initialize parser with a PDF file.
        
        Args:
            pdf_path: Path to the PDF file
        """
        self.pdf_path = pdf_path
        self.pdf = None
        self.current_chapter = None
        self.current_section = None
    
    def parse(self) -> List[ParsedPage]:
        """
        Parse entire PDF and return list of ParsedPage objects.
        
        Returns:
            List of ParsedPage objects with chapter/section metadata
        """
        parsed_pages = []
        
        with pdfplumber.open(self.pdf_path) as pdf:
            self.pdf = pdf
            chapter_num = 0
            current_chapter_title = None
            
            for page_idx, page in enumerate(pdf.pages):
                page_num = page_idx + 1
                
                # Extract text and detect headings
                text = self._extract_page_text(page)
                headings = self._detect_headings(page)
                
                # Update chapter/section context
                for heading in headings:
                    if heading["level"] == "chapter":
                        chapter_num += 1
                        current_chapter_title = heading["text"]
                        self.current_section = None
                    elif heading["level"] == "section":
                        self.current_section = heading["text"]
                
                # Create parsed page object
                parsed_page = ParsedPage(
                    page_num=page_num,
                    chapter_num=chapter_num if chapter_num > 0 else None,
                    chapter_title=current_chapter_title,
                    section_title=self.current_section,
                    raw_text=text
                )
                
                parsed_pages.append(parsed_page)
        
        return parsed_pages
    
    def _extract_page_text(self, page) -> str:
        """
        Extract text from a page, handling multi-column layouts.
        
        Args:
            page: pdfplumber Page object
            
        Returns:
            Extracted text with headers/footers stripped
        """
        try:
            # Try cropping to remove headers and footers
            # Assume header in top 0.5 inch, footer in bottom 0.5 inch
            height = page.height
            width = page.width
            
            # Crop margins (0.5 inch = 36 points)
            cropped_page = page.within_bbox((36, 36, width - 36, height - 36))
            text = cropped_page.extract_text()
            
            # Clean up text: remove multiple spaces, normalize line breaks
            if text:
                text = re.sub(r'\s+', ' ', text)  # Collapse whitespace
                text = re.sub(r"[^\w\s।,.\-?!()//—]", '', text, flags=re.UNICODE)  # Remove junk chars but keep Indian punctuation
                text = text.strip()
            
            return text or ""
        except Exception as e:
            print(f"⚠️  Error extracting text from page {page.page_number}: {e}")
            return ""
    
    def _detect_headings(self, page) -> List[Dict]:
        """
        Detect chapter and section headings using font size heuristics.
        
        Args:
            page: pdfplumber Page object
            
        Returns:
            List of heading dicts with keys: text, level (chapter/section), size, y_coord
        """
        headings = []
        
        try:
            chars = page.chars
            if not chars:
                return headings
            
            # Group characters by y-coordinate (same line)
            lines = {}
            for char in chars:
                y = round(char["top"], 1)  # Round to group same lines
                if y not in lines:
                    lines[y] = []
                lines[y].append(char)
            
            # Analyze each line for heading characteristics
            for y, chars_in_line in sorted(lines.items()):
                if not chars_in_line:
                    continue
                
                # Get average font size for line
                avg_size = sum(c.get("size", 10) for c in chars_in_line) / len(chars_in_line)
                
                # Extract text from line
                text = "".join(c.get("text", "") for c in chars_in_line).strip()
                
                if not text or len(text) < 3:
                    continue
                
                # Classify heading level by size
                if avg_size >= self.CHAPTER_HEADING_MIN_SIZE:
                    # Further filter: likely all-caps or very short
                    if len(text) < 100:
                        headings.append({
                            "text": text,
                            "level": "chapter",
                            "size": avg_size,
                            "y": y
                        })
                elif avg_size >= self.SECTION_HEADING_MIN_SIZE:
                    if len(text) < 80:
                        headings.append({
                            "text": text,
                            "level": "section",
                            "size": avg_size,
                            "y": y
                        })
        
        except Exception as e:
            print(f"⚠️  Error detecting headings on page {page.page_number}: {e}")
        
        return headings
    
    def get_metadata(self) -> Dict:
        """
        Extract PDF metadata (title, author, creation date, page count).
        
        Returns:
            Dictionary with PDF metadata
        """
        with pdfplumber.open(self.pdf_path) as pdf:
            metadata = pdf.metadata or {}
            return {
                "title": metadata.get("Title", ""),
                "author": metadata.get("Author", ""),
                "subject": metadata.get("Subject", ""),
                "pages": len(pdf.pages)
            }
