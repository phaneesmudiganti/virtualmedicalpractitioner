# agents/medication.py
"""
Medication card + generic safety extractor for the Medicines tab.

Keeps original behavior:
- build_medicine_card(query) -> dict(query, rx_classification, llm_summary)
  (now also returns optional: generic_name, drug_class for richer context)

Adds:
- get_medicine_safety_json(query, generic_name?, drug_class?) -> strict JSON dict
  with keys: mandatory_precautions, implications_if_ignored, who_should_avoid,
             how_to_take, source_citations
"""

import json
import pathlib
import re
from typing import Dict, Any

from llm.gemini_client import GeminiClient

DATA_DIR = pathlib.Path(__file__).resolve().parents[1] / "data"
SCHEDULES = json.loads((DATA_DIR / "schedules_subset.json").read_text(encoding="utf-8"))
RX_SCHEDULES = {"H", "H1", "X"}  # Rx-only schedules in India


def classify_rx_status(generic_name: str) -> str:
    g = (generic_name or "").strip().lower()
    for sched, molecules in SCHEDULES.items():
        if g in [m.lower() for m in molecules]:
            return f"Prescription-only (Schedule {sched})"
    return "Likely non-prescription (not listed under H/H1/X); verify label & pharmacist guidance"


def cdsco_dcgi_context_note() -> str:
    return (
        "Regulatory approvals are determined by CDSCO/DCGI (India’s national drug regulator). "
        "IMA is a professional association, not an approval authority."
    )


# --- Lightweight helpers to enrich the card (optional for the UI) ---

def _guess_generic_name(query: str) -> str:
    """
    Very light heuristic: take left side of common separators, trim.
    Users often enter: 'Brand – generic', 'Brand - generic', or just the molecule/brand name.
    """
    if not query:
        return ""
    # Split on en dash or hyphen
    generic_guess = re.split(r"[–-]", query, maxsplit=1)[0].strip()
    # Prefer anything inside parentheses e.g., "Meftal-P (mefenamic acid)"
    m = re.search(r"\(([^)]+)\)", query)
    if m:
        inner = m.group(1).strip()
        if 3 <= len(inner) <= 60:
            return inner
    return generic_guess


_DRUG_CLASS_MAP = {
    # NSAIDs
    "mefenamic": "NSAID",
    "ibuprofen": "NSAID",
    "diclofenac": "NSAID",
    "naproxen": "NSAID",
    # Nitroimidazoles
    "metronidazole": "Nitroimidazole antibiotic",
    "tinidazole": "Nitroimidazole antibiotic",
    # Tetracyclines
    "tetracycline": "Tetracycline antibiotic",
    "doxycycline": "Tetracycline antibiotic",
    "minocycline": "Tetracycline antibiotic",
    # Fluoroquinolones
    "ciprofloxacin": "Fluoroquinolone antibiotic",
    "levofloxacin": "Fluoroquinolone antibiotic",
    "ofloxacin": "Fluoroquinolone antibiotic",
    "moxifloxacin": "Fluoroquinolone antibiotic",
    # Statins
    "atorvastatin": "Statin",
    "simvastatin": "Statin",
    "lovastatin": "Statin",
    "rosuvastatin": "Statin",
    "pravastatin": "Statin",
    "pitavastatin": "Statin",
    # ACE inhibitors / ARBs
    "lisinopril": "ACE inhibitor",
    "ramipril": "ACE inhibitor",
    "enalapril": "ACE inhibitor",
    "perindopril": "ACE inhibitor",
    "losartan": "ARB",
    "valsartan": "ARB",
    "telmisartan": "ARB",
    "olmesartan": "ARB",
    # Anticoagulants (VKA)
    "warfarin": "Vitamin K antagonist (anticoagulant)",
    "acenocoumarol": "Vitamin K antagonist (anticoagulant)",
}

def _guess_drug_class(text: str) -> str:
    t = (text or "").lower()
    for key, cls in _DRUG_CLASS_MAP.items():
        if key in t:
            return cls
    return ""


# --- Your original function, preserved and slightly enriched ---

def build_medicine_card(query: str) -> Dict[str, Any]:
    """
    Build a medicine info card with: generic, Rx/OTC classification, precautions,
    contraindications, common side effects, and India availability notes.

    Returns (backward compatible):
      {
        "query": <str>,
        "rx_classification": <str>,
        "llm_summary": <str> or <markdown>,
        # new (optional):
        "generic_name": <str>,
        "drug_class": <str>,
      }
    """
    client = GeminiClient()
    system = (
        "You are a pharmacology summarizer for the Indian context. "
        "Include whether the medicine is Rx-only (Schedules H/H1/X) if known, "
        "typical adult dosing ranges (DO NOT prescribe), key precautions "
        "(pregnancy, renal/hepatic, interactions), and availability in India. "
        "Cite that approvals are by CDSCO/DCGI."
    )
    resp_text = client.chat(
        [{"role": "user", "parts": [f"Medicine query: {query}\nNote: {cdsco_dcgi_context_note()}"]}],
        system=system,
    )

    generic_guess = _guess_generic_name(query)
    rx_label = classify_rx_status(generic_guess)
    drug_class = _guess_drug_class(f"{query} {resp_text} {generic_guess}")

    return {
        "query": query,
        "rx_classification": rx_label,
        "llm_summary": resp_text,
        "generic_name": generic_guess,    # optional (helps safety prompt)
        "drug_class": drug_class,         # optional (helps safety prompt)
    }


# --- Generic safety extractor for highlighting RED boxes in UI ---
# IMPORTANT: escape literal JSON braces with double {{ }} so .format() only substitutes our 3 placeholders.
_SAFETY_PROMPT = """
You are a cautious, India-aware medication safety assistant for the general public.
Return ONLY strict JSON (no prose), with this schema:
{{
  "mandatory_precautions": [string, ...],
  "implications_if_ignored": [string, ...],
  "who_should_avoid": [string, ...],
  "how_to_take": [string, ...],
  "source_citations": [string, ...]
}}
Rules:
- Plain language; each bullet ≤ 18 words.
- No prescribing; avoid exact doses unless essential to a safety point.
- Prefer authoritative sources (drug monographs, regulators, IAP/IPC/IAM guidelines).
- If uncertain, omit; do not guess.
- If nothing credible found, return empty arrays.

Drug query: "{query}"
Generic name: "{generic}"
Class: "{drug_class}"
"""

def _parse_json_loose(s: str) -> dict:
    """Try json.loads; if it fails, extract trailing {...} with regex."""
    if not s:
        return {}
    s = s.strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    m = re.search(r"\{.*\}\s*$", s, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}
    return {}


def get_medicine_safety_json(query: str, generic_name: str = "", drug_class: str = "") -> Dict[str, Any]:
    """
    Ask the LLM for structured safety info to drive 'Mandatory Precautions' and
    'Implications if ignored' highlighting in the UI. Returns required keys; empty lists if none.
    """
    client = GeminiClient()
    prompt = _SAFETY_PROMPT.format(query=query or "", generic=generic_name or "", drug_class=drug_class or "")

    # Ask for JSON-only
    resp = client.gmodel.generate_content(
        [{"role": "user", "parts": [prompt]}],
        generation_config={"temperature": 0.2, "response_mime_type": "application/json"},
        safety_settings=None,
    )
    text = getattr(resp, "text", "") or ""
    data = _parse_json_loose(text)

    # Normalize required keys
    out = {
        "mandatory_precautions": data.get("mandatory_precautions") or [],
        "implications_if_ignored": data.get("implications_if_ignored") or [],
        "who_should_avoid": data.get("who_should_avoid") or [],
        "how_to_take": data.get("how_to_take") or [],
        "source_citations": data.get("source_citations") or [],
    }
    return out


__all__ = [
    "build_medicine_card",
    "get_medicine_safety_json",
    "classify_rx_status",
]