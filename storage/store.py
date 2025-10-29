from sqlalchemy import create_engine, Column, Integer, LargeBinary, String, Text, DateTime, func
from sqlalchemy.orm import declarative_base, sessionmaker
from security.crypto import encrypt_json, decrypt_json
from core.config import settings

Base = declarative_base()
engine = create_engine(f"sqlite:///{settings.DB_PATH}", future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

class Patient(Base):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True)
    pii = Column(LargeBinary, nullable=False)  # encrypted JSON (name, age, id, contact)
    created_at = Column(DateTime, server_default=func.now())

class Consent(Base):
    __tablename__ = "consents"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    meta_blob = Column(LargeBinary, nullable=False)  # encrypted JSON (purposes, language, time)
    created_at = Column(DateTime, server_default=func.now())

class Consultation(Base):
    __tablename__ = "consultations"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, nullable=False)
    transcript = Column(LargeBinary, nullable=False)  # encrypted JSON dialogue
    assessment = Column(LargeBinary, nullable=True)   # encrypted JSON assessment/plan
    created_at = Column(DateTime, server_default=func.now())

class Audit(Base):
    __tablename__ = "audit"
    id = Column(Integer, primary_key=True)
    action = Column(String(64), nullable=False)
    actor = Column(String(64), nullable=False)  # "ai", "user", "doctor"
    resource = Column(String(64), nullable=False)
    details = Column(LargeBinary, nullable=False)
    at = Column(DateTime, server_default=func.now())

def init_db():
    Base.metadata.create_all(engine)

def save_patient(session, pii_dict) -> int:
    p = Patient(pii=encrypt_json(pii_dict))
    session.add(p); session.commit()
    return p.id

def get_patient(session, pid: int):
    p = session.get(Patient, pid)
    return decrypt_json(p.pii) if p else None

def save_consent(session, patient_id: int, text: str, meta: dict) -> int:
    c = Consent(patient_id=patient_id, text=text, meta_blob=encrypt_json(meta))
    session.add(c); session.commit()
    return c.id

def save_consultation(session, patient_id: int, transcript: dict, assessment: dict | None):
    cons = Consultation(patient_id=patient_id,
                        transcript=encrypt_json(transcript),
                        assessment=encrypt_json(assessment) if assessment else encrypt_json({}))
    session.add(cons); session.commit(); return cons.id

def audit(session, action: str, actor: str, resource: str, details: dict):
    a = Audit(action=action, actor=actor, resource=resource, details=encrypt_json(details))
    session.add(a); session.commit()