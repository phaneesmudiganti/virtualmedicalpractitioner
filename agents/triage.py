# agents/triage.py
"""
Stateful triage agent (Gemini 2.5 Flash) with doctor-like tone and minimal constraints.

Design goals
------------
- Let the LLM adapt to the user's own words and flow.
- Keep outputs as STRICT JSON so the UI remains stable.
- Avoid rigid heuristics and pre-scripted Q&A trees.
- Provide only gentle, generic fallbacks if the model fails to return valid JSON.
- Avoid asking the exact same question repeatedly.

I/O contracts
-------------
- Conversation history (LLM-native format) is a list of dicts:
    [{"role": "user" | "model", "parts": [text]}, ...]
  (This is distinct from the Gradio Chatbot messages format used in the UI.)
- Entry point returns: (result_json, assistant_reply, updated_history)
  where `assistant_reply` is the first string in `result_json["questions_next"]`.
"""

from typing import List, Dict, Optional, Tuple
import json
import re

from llm.gemini_client import GeminiClient
from core.constants import AI_DISCLOSURE, EMERGENCY_BANNER

# ---------------------------------------------------------------------
# System instruction: doctor-like, adaptive, JSON-only, minimal guardrails
# ---------------------------------------------------------------------
TRIAGE_SYSTEM = (
    "ROLE: You are an empathetic, India-aware clinical triage assistant, responding as a doctor would.\n"
    "TONE: Warm, respectful, concise; use plain language. Acknowledge what the patient already said.\n"
    "GOAL: Understand the patient's concern, ask focused follow-ups, note any red flags, and share safe self-care guidance.\n"
    "IMPORTANT:\n"
    "- Adapt questions to what the patient already provided; DO NOT ask for the same detail again.\n"
    "- Ask only 1–2 concise questions per turn, specific to this patient's context.\n"
    "- Do NOT provide diagnosis or prescriptions. If red flags emerge, advise urgent care.\n"
    "OUTPUT: Return ONLY valid JSON (no markdown, no preface) with this schema:\n"
    "{\n"
    '  \"questions_next\": [string, ...],\n'
    '  \"red_flags\": [string, ...],\n'
    '  \"summary\": string,\n'
    '  \"self_care_advice\": string\n'
    "}\n"
)

# Gentle generic questions used ONLY when the model fails or repeats
_GENTLE_FALLBACKS = [
    "Thanks for sharing. What else about your symptoms would you like me to know right now?",
    "Is there anything that makes your symptoms better or worse? Have you noticed any new changes?",
    "Have you taken anything or tried any home care yet? How are you feeling overall at the moment?"
]

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def _try_parse_json(text: str) -> Optional[dict]:
    """Parse JSON; if extra text surrounds it, extract the trailing JSON object."""
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}\s*$", text, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None

def _last_assistant_turn(history: List[Dict[str, str]]) -> Optional[str]:
    """Return the last assistant (model) message text, if any."""
    for msg in reversed(history or []):
        if msg.get("role") == "model":
            parts = msg.get("parts") or []
            return parts[0] if parts else None
    return None

def _non_repetitive(candidate: str, last_bot: Optional[str]) -> str:
    """
    If the model's next question equals the last assistant question (or is nearly identical),
    switch to a gentle, open-ended fallback to avoid loops.
    """
    c = (candidate or "").strip()
    lb = (last_bot or "").strip()
    if not c:
        return _GENTLE_FALLBACKS[0]
    # Simple repetition check (case-insensitive, ignore trailing punctuation)
    canon_c = re.sub(r"[^\w\s]", "", c.lower())
    canon_lb = re.sub(r"[^\w\s]", "", lb.lower())
    if canon_c and canon_c == canon_lb:
        # rotate through a few gentle variations
        # simple deterministic pick based on length to avoid adding external state
        idx = len(canon_c) % len(_GENTLE_FALLBACKS)
        return _GENTLE_FALLBACKS[idx]
    return c

def _safe_questions_list(obj) -> List[str]:
    """Coerce questions_next to a short list of strings (1–2 items)."""
    if isinstance(obj, list):
        qs = [str(x) for x in obj if isinstance(x, (str, int, float))]
    elif isinstance(obj, (str, int, float)):
        qs = [str(obj)]
    else:
        qs = []
    # Keep it brief to reduce burden
    return qs[:2] if qs else []

def _gentle_json_fallback() -> dict:
    """Minimal, non-leading JSON fallback; used only when the model fails completely."""
    return {
        "questions_next": [_GENTLE_FALLBACKS[0]],
        "red_flags": [],
        "summary": "Collecting symptom details based on the patient's own words.",
        "self_care_advice": (
            "Please rest and stay hydrated. If you experience severe or rapidly worsening symptoms "
            "(such as chest pain, breathlessness, confusion, severe weakness), seek urgent care."
        ),
    }

# ---------------------------------------------------------------------
# Core entry point
# ---------------------------------------------------------------------
def start_triage(
    history: List[Dict[str, str]],
    user_msg: Optional[str] = None
) -> Tuple[dict, str, List[Dict[str, str]]]:
    """
    Run one triage step with minimal constraints (trust the LLM to adapt to the user).

    Parameters
    ----------
    history : list[dict]
        Gemini-native conversation history:
          [{"role":"user"|"model", "parts":[text]}, ...]
    user_msg : str | None
        Optional user turn to append before invocation.

    Returns
    -------
    result_json : dict
        Strict JSON object with keys: questions_next, red_flags, summary, self_care_advice.
    assistant_reply : str
        The first question in `questions_next` (used by the UI Chatbot).
    updated_history : list[dict]
        The history including the assistant's new turn appended.
    """
    client = GeminiClient()
    history = history or []

    # Append current user turn
    if user_msg:
        history.append({"role": "user", "parts": [user_msg]})

    last_bot = _last_assistant_turn(history)

    # Build message list (include disclosure / banner and the system instruction up front)
    messages = [
        {"role": "user", "parts": [TRIAGE_SYSTEM]},
        {"role": "user", "parts": [AI_DISCLOSURE]},
        {"role": "user", "parts": [EMERGENCY_BANNER]},
    ] + history

    # Slight creativity so the agent adapts naturally; still ask for JSON-only
    generation_config = {
        "temperature": 0.2,
        "response_mime_type": "application/json",
    }

    # ---- First attempt
    resp = client.gmodel.generate_content(
        messages,
        generation_config=generation_config,
        safety_settings=None,
    )
    text = resp.text or ""
    data = _try_parse_json(text)

    if data:
        # Ensure questions_next is present and concise
        qs = _safe_questions_list(data.get("questions_next"))
        if not qs:
            qs = _safe_questions_list(data.get("summary")) or _GENTLE_FALLBACKS[:1]

        # Avoid repetition with the last assistant question
        qs[0] = _non_repetitive(qs[0], last_bot)

        # Normalize required fields
        data["questions_next"] = qs
        data["red_flags"] = list(data.get("red_flags") or [])
        data["summary"] = str(data.get("summary") or "Triage in progress based on patient input.")
        data["self_care_advice"] = str(
            data.get("self_care_advice") or
            "Please rest and stay hydrated. Seek urgent care if severe symptoms develop."
        )

        assistant_reply = data["questions_next"][0]
        history.append({"role": "model", "parts": [assistant_reply]})
        return data, assistant_reply, history

    # ---- Repair pass (ask the model to return STRICT JSON only)
    repair_msgs = messages + [
        {"role": "user", "parts": ["Return the same content STRICTLY as JSON matching the schema ONLY. No extra text."]},
    ]
    resp2 = client.gmodel.generate_content(
        repair_msgs,
        generation_config=generation_config,
        safety_settings=None,
    )
    text2 = resp2.text or ""
    data2 = _try_parse_json(text2)

    if data2:
        qs2 = _safe_questions_list(data2.get("questions_next"))
        if not qs2:
            qs2 = _safe_questions_list(data2.get("summary")) or _GENTLE_FALLBACKS[:1]

        qs2[0] = _non_repetitive(qs2[0], last_bot)

        data2["questions_next"] = qs2
        data2["red_flags"] = list(data2.get("red_flags") or [])
        data2["summary"] = str(data2.get("summary") or "Triage in progress based on patient input.")
        data2["self_care_advice"] = str(
            data2.get("self_care_advice") or
            "Please rest and stay hydrated. Seek urgent care if severe symptoms develop."
        )

        assistant_reply2 = data2["questions_next"][0]
        history.append({"role": "model", "parts": [assistant_reply2]})
        return data2, assistant_reply2, history

    # ---- Final gentle fallback (model failed twice)
    jf = _gentle_json_fallback()
    jf["questions_next"][0] = _non_repetitive(jf["questions_next"][0], last_bot)
    assistant_reply_fb = jf["questions_next"][0]
    history.append({"role": "model", "parts": [assistant_reply_fb]})
    return jf, assistant_reply_fb, history