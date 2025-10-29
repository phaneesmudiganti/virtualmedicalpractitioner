# Virtual Medical Practitioner (India) — Gemini 2.5 Flash

> **AI Disclosure:** You are interacting with an AI triage assistant. A licensed medical doctor will review the case and issue the final prescription. In an emergency, seek immediate care.

## Features
- Conversational triage (asks relevant questions, flags red‑flags).
- Medicine info for India: Rx vs non‑prescription; precautions, contraindications.
- Identity verification (PAN/Aadhaar format), consent capture (DPDP).
- Encrypted record storage, audit log, anonymization.
- Bias‑mitigation hooks and clinical validation stub.

## Regulatory & Compliance (India)
- **Approvals:** By **CDSCO/DCGI** (not IMA).  
- **Rx vs OTC:** Driven by **Schedules H/H1/X**; India has no formal statutory OTC list—unlisted medicines are typically sold without prescription under pharmacist guidance.  
- **Privacy:** **DPDP Act, 2023** (notice/consent, rights, penalties) + legacy **IT Act s.43A/SPDI Rules**; **ABDM** consent & security patterns for future integration.  
- **Retention:** Keep indoor patient records ≥ **3 years** (legacy MCI/NMC ethics); adapt to hospital/NABH policies.

**Key sources**:  
DPDP: MeitY Gazette; PwC explainer.  
CDSCO/DCGI: CDSCO Home & Functions pages.  
OTC vs Rx: OPPI FAQ; Schedule H/H1 explainers.  
Retention: IMA/MCI article; CAHO retention guide.

## Quickstart
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # add GOOGLE GEMINI API KEY
uvicorn web.api:app --host 0.0.0.0 --port 8000 --reload
``
