import time
import warnings
import logging
# Suppress Google API version and package deprecation warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

import google.generativeai as genai
from typing import Dict, Any, Optional, Generator
from google.generativeai.types import generation_types
from src.core.llm_provider import LLMProvider

logger = logging.getLogger(__name__)

class GeminiProvider(LLMProvider):
    def __init__(self, model_name: str = "gemini-2.5-flash", api_key: Optional[str] = None):
        super().__init__(model_name, api_key)
        genai.configure(api_key=self.api_key)

        self.config = genai.GenerationConfig(
            temperature=0.0,
            top_p=0.95,
            top_k=40
        )

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        start_time = time.time()

        try:
            if system_prompt:
                model = genai.GenerativeModel(
                    model_name=self.model_name,
                    system_instruction=system_prompt
                )
            else:
                model = genai.GenerativeModel(model_name=self.model_name)

            response = model.generate_content(
                prompt,
                generation_config=self.config
            )

            end_time = time.time()
            latency_ms = int((end_time - start_time) * 1000)

            usage_metadata = getattr(response, 'usage_metadata', None)
            usage = {
                "prompt_tokens": usage_metadata.prompt_token_count if usage_metadata else 0,
                "completion_tokens": usage_metadata.candidates_token_count if usage_metadata else 0,
                "total_tokens": usage_metadata.total_token_count if usage_metadata else 0
            }

            # Check if response was blocked
            if not response.candidates:
                logger.warning("Gemini response blocked - no candidates returned")
                return {"error": "Response blocked by safety filters", "content": "", "usage": usage, "latency_ms": latency_ms, "provider": "google"}

            candidate = response.candidates[0]

            # Check finish reason
            finish_reason = getattr(candidate, 'finish_reason', None)
            if finish_reason and finish_reason.name != 'STOP':
                logger.warning(f"Gemini finish reason: {finish_reason.name}")

            # Safely extract text from response
            content = ""
            try:
                content = response.text
            except Exception as e:
                logger.warning(f"Failed to get response.text: {e}")
                # Try to extract from parts
                if hasattr(candidate, 'content') and candidate.content.parts:
                    content = "".join(part.text for part in candidate.content.parts if hasattr(part, 'text'))

            if not content:
                logger.warning("Gemini returned empty content")

            return {
                "content": content,
                "usage": usage,
                "latency_ms": latency_ms,
                "provider": "google"
            }

        except generation_types.StopCandidateException as e:
            logger.error(f"Gemini StopCandidateException: {e}")
            return {"error": "Content flagged by safety filters.", "content": ""}
        except Exception as e:
            logger.error(f"Gemini API error: {str(e)}", exc_info=True)
            return {"error": f"Error connected Gemini API: {str(e)}", "content": ""}

    def stream(self, prompt: str, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        if system_prompt:
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=system_prompt
            )
        else:
            model = genai.GenerativeModel(model_name=self.model_name)

        try:
            response = model.generate_content(
                prompt, 
                generation_config=self.config,
                stream=True
            )
            for chunk in response:
                yield chunk.text
        except Exception as e:
            yield f"\n[Stream Error: {str(e)}]"