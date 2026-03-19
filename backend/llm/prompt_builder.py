"""
Prompt Builder Module

Assembles system and user prompts for Claude.
Respects token budget and optimal prompt structure.
"""

import logging
from typing import List, Optional
from backend.database import Chunk
from backend.config import settings

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Builds optimized prompts for Claude Haiku within token limits."""
    
    def __init__(self, grade: int = 8, language: str = "english"):
        """
        Initialize prompt builder.
        
        Args:
            grade: Student grade level (6-10 for Indian curriculum)
            language: Response language
        """
        self.grade = grade
        self.language = language
    
    def build_system_prompt(self) -> str:
        """
        Build system prompt for VidyaBot tutor role.
        Curriculum-focused, encouraging, honest about limitations.
        
        Returns:
            System prompt string
        """
        if self.language == "english":
            return f"""You are VidyaBot, a patient and encouraging tutor for Indian school students in grade {self.grade}.

Your Role:
- Answer questions ONLY from the provided textbook context
- Be concise and clear (maximum 150 words)
- Use simple language appropriate for a grade {self.grade} student
- Include examples from the textbook when helpful
- Explain WHY, not just WHAT

Important Rules:
1. If the answer is NOT in the provided textbook context, say clearly: "This topic isn't covered in your textbook. Please ask your teacher or check a different resource."
2. NEVER make up information or use knowledge outside the textbook
3. NEVER provide answers to homework from unstated problem book (if it seems like copying, refuse)
4. If a student asks multiple questions, answer them one by one
5. Be encouraging and supportive - make learning feel achievable

Format:
- Start with a clear, direct answer
- Add key points as bullet points if helpful
- End with a short encouraging note
- If mentioning a page or section, cite it: "(Chapter 3, Page 45)"

Remember: You're tutoring government school students with limited resources. Be patient, clear, and honest."""
        
        else:
            # For other languages, provide bilingual support
            return f"""You are VidyaBot, a student tutor.

Answer ONLY from the provided textbook context.
Be concise and use simple language for grade {self.grade}.
If the answer is not in the textbook, say: "This is not in your textbook."
Never make up information."""
    
    def build_user_prompt(self, question: str, chunks: List[Chunk]) -> str:
        """
        Build user prompt with question and relevant textbook context.
        Carefully formatted for optimal LLM comprehension within token budget.
        
        Args:
            question: Student's question
            chunks: List of relevant chunks from textbook
            
        Returns:
            Complete user prompt with context
        """
        if not chunks:
            return f"Question: {question}\n\n(No relevant context found in textbook)"
        
        # Build context section
        context_sections = []
        
        for i, chunk in enumerate(chunks, 1):
            # Format chunk with metadata
            section = f"[Textbook Excerpt {i}]\n"
            
            if chunk.chapter_title:
                section += f"Chapter: {chunk.chapter_title}\n"
            
            if chunk.section_title:
                section += f"Section: {chunk.section_title}\n"
            
            if chunk.page_number:
                section += f"Page: {chunk.page_number}\n"
            
            section += f"\n{chunk.content.strip()}\n"
            
            context_sections.append(section)
        
        # Assemble final prompt
        prompt = f"""Context from your textbook:

{chr(10).join(context_sections)}

Question: {question}

Answer the question using ONLY the context provided above."""
        
        return prompt
    
    def build_socratic_prompt(self, question: str, chunks: List[Chunk]) -> str:
        """
        Build a Socratic prompt that asks guiding questions instead of giving direct answers.
        Useful for exam preparation and deeper learning.
        
        Args:
            question: Student's question
            chunks: List of relevant textbook chunks
            
        Returns:
            Socratic prompt with guiding questions
        """
        if not chunks:
            return f"I don't have enough information to guide you on this question. Ask your teacher about: {question}"
        
        system_part = """You are a Socratic tutor. Help students learn by asking guiding questions instead of giving direct answers.

Your approach:
1. Ask what the student already knows
2. Ask them to find relevant information in the textbook
3. Guide them with questions toward the answer
4. Never give the answer directly

Keep responses short (max 100 words)."""
        
        context = "\n".join(
            f"[Excerpt {i}] {chunk.content[:100]}..."
            for i, chunk in enumerate(chunks, 1)
        )
        
        user_part = f"""Relevant textbook material:
{context}

Student question: {question}

Help them learn using guiding questions."""
        
        return f"{system_part}\n\n{user_part}"
    
    def build_quiz_prompt(self, chunks: List[Chunk], num_questions: int = 3) -> str:
        """
        Build a quiz prompt - generate study questions from textbook content.
        
        Args:
            chunks: List of textbook chunks to create quiz from
            num_questions: Number of questions to generate
            
        Returns:
            Prompt for generating quiz questions
        """
        if not chunks:
            return "No textbook material available for quiz."
        
        context = "\n".join(
            f"[Section {i}] {chunk.section_title or 'Content'}\n{chunk.content[:150]}..."
            for i, chunk in enumerate(chunks, 1)
        )
        
        return f"""Based on this textbook material, generate {num_questions} study questions:

{context}

Generate {num_questions} questions:
- Mix of easy and hard
- Different question types (fill-in-blank, short answer, explain)
- Answerable from the material provided
- Suitable for a grade {self.grade} student

Format each question clearly and include the answer key."""
    
    def build_translation_prompt(self, text: str, target_language: str) -> str:
        """
        Build prompt for translating concepts (used by translation module).
        
        Args:
            text: Text to translate
            target_language: Target language name
            
        Returns:
            Translation prompt
        """
        return f"""Translate this educational text to {target_language}, keeping the meaning clear for a student.

Text to translate:
{text}

Requirements:
- Keep technical terms accurate
- Use simple {target_language} for a grade {self.grade} student
- Maintain structure and formatting
- Preserve meaning exactly"""
    
    @staticmethod
    def estimate_token_count(text: str) -> int:
        """
        Estimate token count for prompt construction.
        Uses rough heuristic: words * 1.3 (accounts for subword tokenization).
        
        Args:
            text: Text to estimate
            
        Returns:
            Approximate token count
        """
        words = len(text.split())
        return max(1, int(words * 1.3))
