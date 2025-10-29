from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, EmailStr
from storage.store import init_db, SessionLocal, save_patient, save_consent, save_consultation, audit
from agents.identity import identity_payload
from agents.compliance import generate_consent
from agents.triage import start_triage
from agents.medication import build_medicine_card
from core.constants import AI_DISCLOSURE, EMERGENCY_BANNER

app = FastAPI(title="Virtual Medical Practitioner (India)")
init_db()

class IdentityIn(BaseModel):
    name: str
    age: int = Field(ge=0)
    id_proof_type: str = Field(description="PAN or Aadhaar")
    id_value: str
    phone: str
    email: EmailStr | None = None

class ConsentIn(BaseModel):
    patient_id: int
    language: str = "en"

class ChatTurn(BaseModel):
    role: str
    content: str

class TriageIn(BaseModel):
    patient_id: int
    history: list[ChatTurn]

class MedQuery(BaseModel):
    query: str

@app.get("/health")
def health():
    return {"status": "ok", "disclaimer": AI_DISCLOSURE, "emergency": EMERGENCY_BANNER}

@app.post("/identify")
def identify(payload: IdentityIn):
    idp = identity_payload(**payload.model_dump())
    if not idp["verified"]:
        raise HTTPException(400, "Identity verification failed. Check ID format/phone.")
    db = SessionLocal()
    pid = save_patient(db, idp)
    audit(db, "identify", "user", "patient", {"pid": pid})
    return {"patient_id": pid, "verified": True}

@app.post("/consent")
def consent(data: ConsentIn):
    notice = generate_consent(language=data.language)
    db = SessionLocal()
    cid = save_consent(db, data.patient_id, notice["notice"], notice)
    audit(db, "consent", "user", "consent", {"pid": data.patient_id, "cid": cid})
    return {"consent_id": cid, "notice": notice}

@app.post("/triage")
def triage(data: TriageIn):
    messages = [{"role": t.role, "parts": [t.content]} for t in data.history]
    result = start_triage(messages)
    db = SessionLocal()
    cons_id = save_consultation(db, data.patient_id, transcript={"history": data.history}, assessment=result)
    audit(db, "triage", "ai", "consultation", {"pid": data.patient_id, "consultation_id": cons_id})
    return {"consultation_id": cons_id, "triage": result}

@app.post("/medicines")
def medicines(q: MedQuery):
    card = build_medicine_card(q.query)
    return card

# web/api.py  (append at the bottom)

import gradio as gr
from ui.gradio_ui import build_ui

demo = build_ui()
app = gr.mount_gradio_app(app, demo, path="/ui")