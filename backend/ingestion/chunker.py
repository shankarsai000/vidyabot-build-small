"""
Chunking Module

Intelligently chunks parsed PDF pages into small, semantically meaningful pieces.
Groups by chapter/section and enforces token limits with overlap.
"""

from typing import List, Dict, Optional
from dataclasses import dataclass, field
from backend.ingestion.pdf_parser import ParsedPage
from backend.config import settings
import re


@dataclass
class TextChunk:
    """Represents a single text chunk with metadata."""
    textbook_id: Optional[int] = None
    chapter_number: Optional[int] = None
    chapter_title: Optional[str] = None
    section_title: Optional[str] = None
    page_number: int = 0
    chunk_index: int = 0
    content: str = ""
    token_count: int = 0


class Chunker:
    """Chunks parsed PDF pages into token-limited segments."""
    
    def __init__(self, max_chunk_tokens: int = 200, overlap_tokens: int = 20):
        """
        Initialize chunker.
        
        Args:
            max_chunk_tokens: Maximum tokens per chunk (before splitting)
            overlap_tokens: Token overlap for sliding window
        """
        self.max_chunk_tokens = max_chunk_tokens
        self.overlap_tokens = overlap_tokens
    
    def chunk_by_section(self, parsed_pages: List[ParsedPage], 
                         textbook_id: Optional[int] = None) -> List[TextChunk]:
        """
        Group pages by chapter+section, then split long chunks.
        
        Args:
            parsed_pages: List of ParsedPage from PDF parser
            textbook_id: ID of the textbook (optional)
            
        Returns:
            List of TextChunk objects
        """
        chunks = []
        current_chapter_num = None
        current_chapter_title = None
        current_section_title = None
        accumulated_text = ""
        chunk_index = 0
        start_page = 1
        
        for page in parsed_pages:
            # Detect section/chapter changes
            if page.chapter_num != current_chapter_num:
                # Flush accumulated text from previous chapter
                if accumulated_text.strip():
                    section_chunks = self.split_long_chunks(
                        accumulated_text,
                        chapter_num=current_chapter_num,
                        chapter_title=current_chapter_title,
                        section_title=current_section_title,
                        page_number=start_page,
                        textbook_id=textbook_id,
                        start_chunk_index=chunk_index
                    )
                    chunks.extend(section_chunks)
                    chunk_index += len(section_chunks)
                    accumulated_text = ""
                
                current_chapter_num = page.chapter_num
                current_chapter_title = page.chapter_title
                current_section_title = page.section_title
                start_page = page.page_num
            
            elif page.section_title != current_section_title:
                # New section within same chapter
                if accumulated_text.strip():
                    section_chunks = self.split_long_chunks(
                        accumulated_text,
                        chapter_num=current_chapter_num,
                        chapter_title=current_chapter_title,
                        section_title=current_section_title,
                        page_number=start_page,
                        textbook_id=textbook_id,
                        start_chunk_index=chunk_index
                    )
                    chunks.extend(section_chunks)
                    chunk_index += len(section_chunks)
                    accumulated_text = ""
                
                current_section_title = page.section_title
                start_page = page.page_num
            
            # Accumulate page text
            if page.raw_text:
                accumulated_text += " " + page.raw_text
        
        # Flush final section
        if accumulated_text.strip():
            section_chunks = self.split_long_chunks(
                accumulated_text,
                chapter_num=current_chapter_num,
                chapter_title=current_chapter_title,
                section_title=current_section_title,
                page_number=start_page,
                textbook_id=textbook_id,
                start_chunk_index=chunk_index
            )
            chunks.extend(section_chunks)
        
        return chunks
    
    def split_long_chunks(self, text: str, chapter_num: Optional[int] = None,
                         chapter_title: Optional[str] = None,
                         section_title: Optional[str] = None,
                         page_number: int = 0,
                         textbook_id: Optional[int] = None,
                         start_chunk_index: int = 0) -> List[TextChunk]:
        """
        Split long text into chunks respecting token limit with overlap.
        Uses sliding window with configurable overlap.
        
        Args:
            text: Raw text to chunk
            chapter_num: Chapter number
            chapter_title: Chapter title
            section_title: Section title
            page_number: Page number where chunk starts
            textbook_id: Textbook ID
            start_chunk_index: Starting chunk index (for numbering)
            
        Returns:
            List of TextChunk objects
        """
        chunks = []
        
        # Split text into sentences for better semantics
        sentences = self._split_into_sentences(text)
        if not sentences:
            return chunks
        
        current_chunk_sentences = []
        chunk_tokens = 0
        chunk_index = start_chunk_index
        
        for i, sentence in enumerate(sentences):
            sentence_tokens = self.estimate_tokens(sentence)
            
            # Check if adding this sentence exceeds limit
            if chunk_tokens + sentence_tokens > self.max_chunk_tokens and current_chunk_sentences:
                # Save current chunk
                chunk_text = " ".join(current_chunk_sentences)
                chunk = TextChunk(
                    textbook_id=textbook_id,
                    chapter_number=chapter_num,
                    chapter_title=chapter_title,
                    section_title=section_title,
                    page_number=page_number,
                    chunk_index=chunk_index,
                    content=chunk_text.strip(),
                    token_count=chunk_tokens
                )
                chunks.append(chunk)
                chunk_index += 1
                
                # Start new chunk with overlap (last 20% of previous chunk)
                overlap_sentences = int(len(current_chunk_sentences) * 0.2)  # ~20% overlap
                current_chunk_sentences = current_chunk_sentences[max(0, len(current_chunk_sentences) - overlap_sentences):]
                chunk_tokens = sum(self.estimate_tokens(s) for s in current_chunk_sentences)
            
            current_chunk_sentences.append(sentence)
            chunk_tokens += sentence_tokens
        
        # Add final chunk
        if current_chunk_sentences:
            chunk_text = " ".join(current_chunk_sentences)
            chunk = TextChunk(
                textbook_id=textbook_id,
                chapter_number=chapter_num,
                chapter_title=chapter_title,
                section_title=section_title,
                page_number=page_number,
                chunk_index=chunk_index,
                content=chunk_text.strip(),
                token_count=chunk_tokens
            )
            chunks.append(chunk)
        
        return chunks
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences, respecting Indian language punctuation.
        
        Args:
            text: Raw text
            
        Returns:
            List of sentences
        """
        # Add space after common sentence endings
        text = re.sub(r'([.?!।])([^\s])', r'\1 \2', text)
        
        # Split on period, question mark, exclamation, Devanagari danda
        sentences = re.split(r'[.?!।]+', text)
        
        # Clean and filter empty sentences
        sentences = [s.strip() for s in sentences if s.strip()]
        
        return sentences
    
    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Estimate token count using simple heuristic: len(text.split()) * 1.3
        
        This is fast and approximately accurate for English and Indian languages.
        1 token ≈ 0.75 words, so we use 1.3 words as conservative estimate.
        
        Args:
            text: Text to estimate
            
        Returns:
            Approximate token count
        """
        words = len(text.split())
        # Conservative estimate: account for subword tokenization
        return max(1, int(words * 1.3))
    
    def get_stats(self, chunks: List[TextChunk]) -> Dict:
        """
        Calculate chunking statistics.
        
        Args:
            chunks: List of chunks
            
        Returns:
            Statistics dictionary
        """
        if not chunks:
            return {
                "total_chunks": 0,
                "total_tokens": 0,
                "avg_tokens_per_chunk": 0,
                "max_tokens": 0,
                "min_tokens": 0
            }
        
        token_counts = [c.token_count for c in chunks]
        total_tokens = sum(token_counts)
        
        return {
            "total_chunks": len(chunks),
            "total_tokens": total_tokens,
            "avg_tokens_per_chunk": total_tokens / len(chunks),
            "max_tokens": max(token_counts),
            "min_tokens": min(token_counts),
            "chapters": len(set(c.chapter_number for c in chunks if c.chapter_number))
        }
