import json, pathlib, re
from llm.gemini_client import GeminiClient

DATA_DIR = pathlib.Path(__file__).resolve().parents[1] / "data"
SCHEDULES = json.loads((DATA_DIR / "schedules_subset.json").read_text(encoding="utf-8"))
RX_SCHEDULES = {"H", "H1", "X"}  # Rx-only schedules in India

def classify_rx_status(generic_name: str) -> str:
    g = generic_name.strip().lower()
    for sched, molecules in SCHEDULES.items():
        if g in [m.lower() for m in molecules]:
            return f"Prescription-only (Schedule {sched})"
    return "Likely non-prescription (not listed under H/H1/X); verify label & pharmacist guidance"

def cdsco_dcgi_context_note():
    return ("Regulatory approvals are determined by CDSCO/DCGI (India’s national drug regulator). "
            "IMA is a professional association, not an approval authority. ")

def build_medicine_card(query: str) -> dict:
    """
    Build a medicine info card with: generic, Rx/OTC classification, precautions,
    contraindications, common side effects, and India availability notes.
    """
    client = GeminiClient()
    system = (
        "You are a pharmacology summarizer for the Indian context. "
        "Include whether the medicine is Rx-only (Schedules H/H1/X) if known, "
        "typical adult dosing ranges (DO NOT prescribe), key precautions "
        "(pregnancy, renal/hepatic, interactions), and availability in India. "
        "Cite that approvals are by CDSCO/DCGI."
    )
    resp = client.chat([{"role":"user","parts":[f"Medicine query: {query}\n"
                                               f"Note: {cdsco_dcgi_context_note()}"]}],
                       system=system)
    generic_guess = re.split(r"[–|-]", query)[0].strip()
    rx_label = classify_rx_status(generic_guess)
    return {"query": query, "rx_classification": rx_label, "llm_summary": resp}