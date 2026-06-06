"""
Ollama LLM Client Module

Wrapper around local Ollama inference server for offline-first AI tutoring.
Drop-in replacement for ClaudeClient — same interface, same LLMResponse DTO.
Uses llama.cpp runtime via Ollama for ≤32B parameter models.
"""

import logging
import time
import asyncio
import requests
import json
from typing import Optional, Dict, Generator
from backend.config import settings
from backend.database import LLMResponse

logger = logging.getLogger(__name__)


class OllamaClient:
    """Communicates with local Ollama server for offline inference."""
    
    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 2
    
    def __init__(
        self,
        base_url: str = None,
        model: str = None,
        max_tokens: int = None,
        temperature: float = None,
        timeout: int = None
    ):
        """
        Initialize Ollama client.
        
        Args:
            base_url: Ollama server URL (default from settings)
            model: Model name (default from settings)
            max_tokens: Max output tokens (default from settings)
            temperature: Generation temperature (default from settings)
            timeout: Request timeout in seconds (default from settings)
        """
        self.base_url = base_url or settings.OLLAMA_BASE_URL
        self.model = model or settings.OLLAMA_MODEL
        self.max_tokens = max_tokens or settings.OLLAMA_MAX_TOKENS
        self.temperature = temperature or settings.OLLAMA_TEMPERATURE
        self.timeout = timeout or settings.OLLAMA_TIMEOUT
    
    async def ask_async(self, system_prompt: str, user_prompt: str,
                        max_tokens: int = 256) -> LLMResponse:
        """
        Ask Ollama a question asynchronously (for FastAPI integration).
        
        Args:
            system_prompt: System context/instructions
            user_prompt: User question + context
            max_tokens: Maximum tokens in response
            
        Returns:
            LLMResponse with answer and token counts
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self.ask,
            system_prompt,
            user_prompt,
            max_tokens
        )
    
    def ask(self, system_prompt: str, user_prompt: str,
            max_tokens: int = 256) -> LLMResponse:
        """
        Ask Ollama a question with retries and error handling.
        
        Uses the /api/chat endpoint for proper system/user message separation.
        Falls back to /api/generate with combined prompt if chat fails.
        
        Args:
            system_prompt: System context/instructions
            user_prompt: User question + context
            max_tokens: Maximum tokens in response
            
        Returns:
            LLMResponse with answer and token counts
        """
        max_tokens = max_tokens or self.max_tokens
        
        for attempt in range(self.MAX_RETRIES):
            try:
                logger.debug(f"Calling Ollama API (attempt {attempt + 1}/{self.MAX_RETRIES})")
                
                start_time = time.time()
                
                # Use /api/chat for proper message roles
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": self.temperature
                    }
                }
                
                response = requests.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=self.timeout
                )
                response.raise_for_status()
                
                result = response.json()
                elapsed = time.time() - start_time
                
                # Extract response
                answer = result.get("message", {}).get("content", "")
                
                # Ollama provides token counts in eval_count / prompt_eval_count
                input_tokens = result.get("prompt_eval_count", self.estimate_tokens(system_prompt + user_prompt))
                output_tokens = result.get("eval_count", self.estimate_tokens(answer))
                
                logger.info(
                    f"✅ Ollama response in {elapsed:.1f}s: {input_tokens} input tokens, "
                    f"{output_tokens} output tokens (model: {self.model})"
                )
                
                return LLMResponse(
                    answer=answer,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    model=self.model
                )
                
            except requests.exceptions.ConnectionError as e:
                logger.error(f"Cannot connect to Ollama at {self.base_url}. Is 'ollama serve' running?")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY_SECONDS)
                    continue
                raise RuntimeError(
                    f"Ollama not reachable at {self.base_url}. "
                    f"Start it with: ollama serve"
                ) from e
                
            except requests.exceptions.Timeout as e:
                logger.warning(f"Ollama request timed out after {self.timeout}s, retrying...")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY_SECONDS)
                    continue
                raise RuntimeError(
                    f"Ollama timed out after {self.timeout}s. "
                    f"The model may be loading — try again."
                ) from e
                
            except requests.exceptions.HTTPError as e:
                logger.error(f"Ollama HTTP error: {e}")
                # If model not found, provide helpful message
                if response.status_code == 404:
                    raise RuntimeError(
                        f"Model '{self.model}' not found. "
                        f"Download it with: ollama pull {self.model}"
                    ) from e
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY_SECONDS)
                    continue
                raise
                
            except Exception as e:
                logger.error(f"Ollama inference error: {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_DELAY_SECONDS)
                    continue
                raise RuntimeError(f"Ollama inference failed: {e}") from e
        
        raise RuntimeError("Failed to get response from Ollama after retries")
    
    def generate_stream(self, system_prompt: str, user_prompt: str,
                        max_tokens: int = 256) -> Generator[str, None, None]:
        """
        Stream response for real-time Gradio UI updates.
        
        Yields tokens as they are generated for immediate display.
        
        Args:
            system_prompt: System context/instructions
            user_prompt: User question + context
            max_tokens: Maximum tokens in response
            
        Yields:
            Individual response tokens/chunks
        """
        max_tokens = max_tokens or self.max_tokens
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": True,
            "options": {
                "num_predict": max_tokens,
                "temperature": self.temperature
            }
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout,
                stream=True
            )
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        token = data.get("message", {}).get("content", "")
                        if token:
                            yield token
                    except json.JSONDecodeError:
                        continue
                        
        except requests.exceptions.ConnectionError:
            yield "[Error: Cannot connect to Ollama. Run 'ollama serve' first.]"
        except Exception as e:
            yield f"[Error: {str(e)}]"
    
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
        return max(1, len(text) // 4)
    
    def validate_connection(self) -> bool:
        """
        Validate that Ollama server is running and model is available.
        
        Returns:
            True if Ollama is reachable and model exists
        """
        try:
            # Check if Ollama is running
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=5
            )
            response.raise_for_status()
            
            # Check if our model is available
            models = response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            
            # Check for exact match or partial match (e.g., "mistral:latest" matches "mistral:latest")
            model_found = any(
                self.model in name or name.startswith(self.model.split(":")[0])
                for name in model_names
            )
            
            if model_found:
                logger.info(f"✅ Ollama connected, model '{self.model}' available")
                return True
            else:
                available = ", ".join(model_names) if model_names else "none"
                logger.warning(
                    f"⚠️  Ollama running but model '{self.model}' not found. "
                    f"Available: {available}. "
                    f"Download with: ollama pull {self.model}"
                )
                return True  # Server is up, just need to pull model
                
        except requests.exceptions.ConnectionError:
            logger.error(
                f"❌ Cannot connect to Ollama at {self.base_url}. "
                f"Start it with: ollama serve"
            )
            return False
        except Exception as e:
            logger.error(f"❌ Ollama validation failed: {e}")
            return False
    
    @classmethod
    def validate_api_key(cls) -> bool:
        """
        Compatibility method — validates Ollama connection instead of API key.
        Drop-in replacement for ClaudeClient.validate_api_key().
        
        Returns:
            True if Ollama is reachable
        """
        client = cls()
        return client.validate_connection()
