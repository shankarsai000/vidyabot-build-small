"""
Claude Haiku LLM Client Module

Wrapper around Anthropic API for Claude Haiku.
Handles retries, cost tracking, and response parsing.
"""

import logging
import time
import asyncio
from typing import Optional, Dict, List
from anthropic import Anthropic, APIError, RateLimitError
from backend.config import settings
from backend.database import LLMResponse

logger = logging.getLogger(__name__)


class ClaudeClient:
    """Communicates with Anthropic Claude Haiku API."""
    
    # Model to use for all student queries (cost-optimized)
    MODEL = settings.MODEL_NAME  # claude-haiku-4-5-20251001
    
    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 2
    
    def __init__(self, api_key: str = settings.ANTHROPIC_API_KEY):
        """
        Initialize Claude client.
        
        Args:
            api_key: Anthropic API key
        """
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set in environment or .env")
        
        self.client = Anthropic(api_key=api_key)
        self.model = self.MODEL
    
    async def ask_async(self, system_prompt: str, user_prompt: str,
                        max_tokens: int = 200) -> LLMResponse:
        """
        Ask Claude a question asynchronously (for FastAPI integration).
        
        Args:
            system_prompt: System context/instructions
            user_prompt: User question + context
            max_tokens: Maximum tokens in response
            
        Returns:
            LLMResponse with answer and token counts
        """
        # Run synchronous call in thread pool
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.ask,
            system_prompt,
            user_prompt,
            max_tokens
        )
    
    def ask(self, system_prompt: str, user_prompt: str,
            max_tokens: int = 200) -> LLMResponse:
        """
        Ask Claude a question with retries and error handling.
        
        Args:
            system_prompt: System context/instructions
            user_prompt: User question + context
            max_tokens: Maximum tokens in response
            
        Returns:
            LLMResponse with answer and token counts
        """
        for attempt in range(self.MAX_RETRIES):
            try:
                logger.debug(f"Calling Claude API (attempt {attempt + 1}/{self.MAX_RETRIES})")
                
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[
                        {
                            "role": "user",
                            "content": user_prompt
                        }
                    ]
                )
                
                # Extract response
                answer = response.content[0].text
                input_tokens = response.usage.input_tokens
                output_tokens = response.usage.output_tokens
                
                logger.info(
                    f"✅ Claude response: {input_tokens} input tokens, "
                    f"{output_tokens} output tokens"
                )
                
                return LLMResponse(
                    answer=answer,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model=self.model
                )
                
            except RateLimitError as e:
                logger.warning(f"Rate limited, retrying in {self.RETRY_DELAY_SECONDS}s...")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY_SECONDS)
                    continue
                raise
                
            except APIError as e:
                logger.error(f"API error: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY_SECONDS)
                    continue
                raise
        
        # Should not reach here
        raise RuntimeError("Failed to get response from Claude after retries")
    
    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Rough estimate of token count for a text.
        Using approximation: 1 token ≈ 4 characters (varies by language).
        
        Args:
            text: Text to estimate
            
        Returns:
            Approximate token count
        """
        # Conservative estimate for safety
        return max(1, len(text) // 4)
    
    @classmethod
    def validate_api_key(cls) -> bool:
        """
        Validate that API key works by making a test call.
        
        Returns:
            True if API key is valid, False otherwise
        """
        try:
            client = cls()
            
            # Make cheap test call
            response = client.client.messages.create(
                model=cls.MODEL,
                max_tokens=10,
                messages=[
                    {
                        "role": "user",
                        "content": "Say 'test' only."
                    }
                ]
            )
            
            logger.info("✅ API key validated successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ API key validation failed: {e}")
            return False
