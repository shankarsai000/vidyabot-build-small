"""
Ollama LLM Client Module

Wrapper around local Ollama inference server for offline-first AI tutoring.
Drop-in replacement for ClaudeClient — same interface, same LLMResponse DTO.
Uses llama.cpp runtime via Ollama for ≤32B parameter models.
Robustly falls back to Claude, HF Inference API, or a structured local Mock Reader so it always runs.
"""

import logging
import time
import asyncio
import requests
import json
import re
import os
from typing import Optional, Dict, Generator
from backend.config import settings
from backend.database import LLMResponse

logger = logging.getLogger(__name__)


class OllamaClient:
    """Communicates with local Ollama server, with cascading cloud and mock fallbacks."""
    
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
        Falls back to Claude API, Hugging Face Inference API, or Mock Reader if offline.
        
        Args:
            system_prompt: System context/instructions
            user_prompt: User question + context
            max_tokens: Maximum tokens in response
            
        Returns:
            LLMResponse with answer and token counts
        """
        max_tokens = max_tokens or self.max_tokens
        
        # Check if local Ollama is responsive
        ollama_failed = False
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=2)
            if resp.status_code != 200:
                ollama_failed = True
        except Exception:
            ollama_failed = True
            
        if not ollama_failed:
            for attempt in range(self.MAX_RETRIES):
                try:
                    logger.debug(f"Calling Ollama API (attempt {attempt + 1}/{self.MAX_RETRIES})")
                    
                    start_time = time.time()
                    
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
                    
                    answer = result.get("message", {}).get("content", "")
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
                    
                except requests.exceptions.HTTPError as e:
                    logger.error(f"Ollama HTTP error: {e}")
                    if response.status_code == 404:
                        fallback = getattr(settings, "OLLAMA_FALLBACK_MODEL", None)
                        if fallback and fallback != self.model:
                            logger.warning(f"Model '{self.model}' not found. Falling back to '{fallback}'...")
                            self.model = fallback
                            if attempt < self.MAX_RETRIES - 1:
                                continue
                    if attempt < self.MAX_RETRIES - 1:
                        time.sleep(self.RETRY_DELAY_SECONDS)
                        continue
                        
                except Exception as e:
                    logger.error(f"Ollama inference error (attempt {attempt + 1}): {e}")
                    if attempt < self.MAX_RETRIES - 1:
                        time.sleep(self.RETRY_DELAY_SECONDS)
                        continue
        
        # Local Ollama failed. Attempt fallbacks.
        logger.warning("Local Ollama failed or offline. Attempting fallback providers...")
        
        # 1. Try Claude if API Key is configured
        claude_resp = self._call_claude_fallback(system_prompt, user_prompt, max_tokens)
        if claude_resp:
            logger.info("✅ Fallback to Claude API successful")
            return claude_resp
            
        # 2. Try Hugging Face Serverless Inference API
        hf_answer = self._call_hf_inference_api(system_prompt, user_prompt, max_tokens)
        if hf_answer:
            logger.info("✅ Fallback to HF Inference API successful")
            return LLMResponse(
                answer=hf_answer,
                input_tokens=self.estimate_tokens(system_prompt + user_prompt),
                output_tokens=self.estimate_tokens(hf_answer),
                model="HF Inference API (cloud)"
            )
            
        # 3. Fallback to Textbook Excerpt Reader (Mock Offline Mode)
        logger.warning("All AI providers failed or offline. Falling back to Mock Offline Reader.")
        mock_answer = self._get_mock_offline_response(user_prompt)
        return LLMResponse(
            answer=mock_answer,
            input_tokens=self.estimate_tokens(system_prompt + user_prompt),
            output_tokens=self.estimate_tokens(mock_answer),
            model="Offline Textbook Reader (Fallback)"
        )
    
    def generate_stream(self, system_prompt: str, user_prompt: str,
                        max_tokens: int = 256) -> Generator[str, None, None]:
        """
        Stream response for real-time Gradio UI updates.
        Falls back gracefully if local Ollama is offline.
        
        Args:
            system_prompt: System context/instructions
            user_prompt: User question + context
            max_tokens: Maximum tokens in response
            
        Yields:
            Individual response tokens/chunks
        """
        max_tokens = max_tokens or self.max_tokens
        
        # Check if local Ollama is responsive
        ollama_failed = False
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=2)
            if resp.status_code != 200:
                ollama_failed = True
        except Exception:
            ollama_failed = True
            
        if not ollama_failed:
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
                return  # Stream completed successfully
            except Exception as e:
                logger.warning(f"Ollama streaming failed: {e}. Trying fallbacks...")
        
        # Try cloud or mock fallbacks
        # 1. Claude Fallback
        if settings.ANTHROPIC_API_KEY:
            try:
                from backend.llm.claude_client import ClaudeClient
                claude = ClaudeClient()
                resp = claude.ask(system_prompt, user_prompt, max_tokens)
                yield resp.answer
                return
            except Exception as e:
                logger.warning(f"Claude streaming fallback failed: {e}")
                
        # 2. HF Inference API Fallback
        hf_success = False
        try:
            for token in self._stream_hf_inference_api(system_prompt, user_prompt, max_tokens):
                hf_success = True
                yield token
            if hf_success:
                return
        except Exception as e:
            logger.warning(f"HF Inference API streaming fallback failed: {e}")
            
        # 3. Direct Textbook Reader (Mock Offline Mode)
        yield "📢 **[Offline Reader Mode]**\n*I am currently unable to connect to the local Ollama AI model (or Hugging Face cloud API). Showing the relevant textbook passages directly:*\n\n---\n\n"
        mock_answer = self._get_mock_offline_response(user_prompt, only_excerpts=True)
        # Yield word by word with micro-delay to simulate typing animation
        for word in mock_answer.split(" "):
            yield word + " "
            time.sleep(0.02)
    
    def _call_claude_fallback(self, system_prompt: str, user_prompt: str, max_tokens: int) -> Optional[LLMResponse]:
        """Try calling Claude if API key is present."""
        if settings.ANTHROPIC_API_KEY:
            try:
                from backend.llm.claude_client import ClaudeClient
                claude = ClaudeClient()
                return claude.ask(system_prompt, user_prompt, max_tokens)
            except Exception as e:
                logger.warning(f"Claude fallback failed: {e}")
        return None

    # Ordered list of free HF Inference API models to try
    HF_FALLBACK_MODELS = [
        "Qwen/Qwen2.5-7B-Instruct",
        "mistralai/Mistral-7B-Instruct-v0.3",
        "HuggingFaceH4/zephyr-7b-beta",
        "microsoft/Phi-3-mini-4k-instruct",
    ]

    def _get_hf_client(self):
        """Get a HuggingFace InferenceClient instance.
        Uses huggingface_hub library which routes through router.huggingface.co
        (reachable from HF Spaces) instead of api-inference.huggingface.co (blocked by DNS).
        """
        token = os.environ.get("HF_TOKEN") or os.environ.get("HF_API_TOKEN")
        if token:
            print(f"[HF API] Using HF_TOKEN (first 8 chars): {token[:8]}...")
        else:
            print("[HF API] WARNING: No HF_TOKEN found. API may be rate-limited.")
        try:
            from huggingface_hub import InferenceClient
            return InferenceClient(token=token)
        except ImportError:
            print("[HF API] huggingface_hub not installed, cannot use InferenceClient")
            return None

    def _call_hf_inference_api(self, system_prompt: str, user_prompt: str, max_tokens: int) -> Optional[str]:
        """Call HF Inference API via huggingface_hub InferenceClient. Tries multiple models."""
        client = self._get_hf_client()
        if client is None:
            return None

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        for model_id in self.HF_FALLBACK_MODELS:
            print(f"[HF API] Trying model: {model_id}...")
            try:
                response = client.chat_completion(
                    model=model_id,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=self.temperature,
                )
                answer = response.choices[0].message.content
                if answer:
                    print(f"[HF API] ✅ Success with {model_id} ({len(answer)} chars)")
                    return answer
                else:
                    print(f"[HF API] {model_id} returned empty answer")
            except Exception as e:
                print(f"[HF API] {model_id} failed: {e}")
                logger.warning(f"HF InferenceClient {model_id} failed: {e}")

        print("[HF API] ❌ All models failed.")
        return None

    def _stream_hf_inference_api(self, system_prompt: str, user_prompt: str, max_tokens: int) -> Generator[str, None, None]:
        """Stream from HF Inference API via huggingface_hub InferenceClient. Tries multiple models."""
        client = self._get_hf_client()
        if client is None:
            return

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        for model_id in self.HF_FALLBACK_MODELS:
            print(f"[HF Stream] Trying model: {model_id}...")
            try:
                stream = client.chat_completion(
                    model=model_id,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=self.temperature,
                    stream=True,
                )
                yielded_any = False
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                        tok = chunk.choices[0].delta.content
                        yielded_any = True
                        yield tok
                if yielded_any:
                    print(f"[HF Stream] ✅ Completed streaming from {model_id}")
                    return  # Success — stop trying other models
                else:
                    print(f"[HF Stream] {model_id} streamed but yielded no content")
            except Exception as e:
                print(f"[HF Stream] {model_id} failed: {e}")
                logger.warning(f"HF stream {model_id} failed: {e}")

        print("[HF Stream] ❌ All models failed for streaming.")

    def _get_mock_offline_response(self, user_prompt: str, only_excerpts: bool = False) -> str:
        """Parse textbook excerpts from the prompt and return them as a clean structured document."""
        excerpts = []
        
        parts = re.split(r'\[(?:Textbook )?Excerpt \d+\]', user_prompt)
        headers = re.findall(r'\[(?:Textbook )?Excerpt \d+\]', user_prompt)
        
        for i, part in enumerate(parts[1:]):
            if "Question:" in part:
                part = part.split("Question:")[0]
                
            header = headers[i] if i < len(headers) else "[Excerpt]"
            lines = part.strip().split("\n")
            metadata = []
            content_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith(("Chapter:", "Section:", "Page:")):
                    metadata.append(stripped)
                else:
                    content_lines.append(line)
                    
            metadata_str = " | ".join(metadata) if metadata else ""
            content_str = "\n".join(content_lines).strip()
            
            excerpt_md = f"### 📖 {header.strip('[]')}"
            if metadata_str:
                excerpt_md += f" ({metadata_str})"
            excerpt_md += f"\n\n{content_str}\n"
            excerpts.append(excerpt_md)
            
        if not excerpts:
            excerpts_text = "*I could not find any relevant excerpts in the query context. Please make sure to search an uploaded textbook.*"
        else:
            excerpts_text = "\n".join(excerpts)
            
        if only_excerpts:
            return excerpts_text
            
        return f"""📢 **[Offline Reader Mode]**
*I am currently unable to connect to the local Ollama AI model (or Hugging Face cloud API). Showing the relevant textbook passages directly:*

---

{excerpts_text}

---
💡 *Note: To enable AI synthesis and explanations, make sure Ollama is running (`ollama serve`) and the model is created.*"""

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
        Falls back to reporting always-run capability if offline.
        """
        try:
            # Check if Ollama is running
            response = requests.get(
                f"{self.base_url}/api/tags",
                timeout=2
            )
            response.raise_for_status()
            
            # Check if our model is available
            models = response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            
            model_found = any(
                self.model in name or name.startswith(self.model.split(":")[0])
                for name in model_names
            )
            
            if model_found:
                logger.info(f"✅ Ollama connected, model '{self.model}' available")
                return True
            else:
                logger.warning(
                    f"⚠️  Ollama running but model '{self.model}' not found. "
                    f"Will use base model or cloud/mock fallbacks."
                )
                return True
                
        except Exception as e:
            logger.info(
                f"ℹ️  Cannot connect to Ollama at {self.base_url}. "
                f"App will use cloud/mock fallbacks (Always-Run Mode active)."
            )
            return True
    
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
