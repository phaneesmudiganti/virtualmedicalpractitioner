# llm/gemini_client.py
from typing import Optional, List, Dict, Any
import google.generativeai as genai

from core.config import settings
from core.logger import get_logger

log = get_logger(__name__)

class GeminiClient:
    """
    Thin wrapper around google-generativeai so the rest of the code can:
      - use .chat(...) for simple calls
      - or use .model.generate_content(...) for advanced control
    """

    def __init__(self, model: Optional[str] = None, generation_config: Optional[Dict[str, Any]] = None):
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY missing. Populate .env or environment.")
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model_name = model or settings.GEMINI_MODEL
        # Keep default config minimal; callers can override per invocation
        self.gmodel = genai.GenerativeModel(self.model_name, generation_config=generation_config)

    @property
    def model(self):
        """
        Compatibility shim so existing code can call client.model.generate_content(...)
        """
        return self.gmodel

    def chat(
        self,
        messages: List[Dict[str, Any]],
        system: Optional[str] = None,
        generation_config: Optional[Dict[str, Any]] = None,
        **kwargs: Any
    ) -> str:
        """
        Simple chat helper.

        Args:
            messages: List of messages in Gemini-compatible format:
                      [{"role": "user"|"model", "parts": [text]}, ...]
            system: Optional system-like instruction (prepended as first turn).
            generation_config: Optional per-call generation config;
                               e.g., {"temperature": 0.0, "response_mime_type": "application/json"}
            kwargs: forwarded to generate_content (e.g., safety_settings=None)

        Returns:
            str: response.text (or empty string if none)
        """
        content = []
        if system:
            # Gemini does not have a dedicated "system" role; we prepend as a user turn
            content.append({"role": "user", "parts": [system]})
        content.extend(messages)

        resp = self.gmodel.generate_content(
            content,
            generation_config=generation_config,
            **kwargs
        )
        return resp.text or ""

# ---- Compatibility alias so imports using LLMClient continue to work
LLMClient = GeminiClient