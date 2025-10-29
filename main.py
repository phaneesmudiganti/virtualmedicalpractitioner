from storage.store import init_db, SessionLocal, save_patient, save_consent
from agents.identity import identity_payload
from agents.compliance import generate_consent
from agents.triage import start_triage

def run_cli():
    init_db()
    print("== Virtual Medical Practitioner (CLI) ==")
    print("Note: You are interacting with an AI. A human doctor will review and issue any prescription.")
    name = input("Name: "); age = int(input("Age: "))
    idt = input("ID Type (PAN/Aadhaar): "); idv = input("ID Value: ")
    phone = input("Phone (10 digits or +91...): ")
    ident = identity_payload(name, age, idt, idv, phone)
    if not ident["verified"]:
        print("Identity verification failed. Exiting.")
        return
    db = SessionLocal(); pid = save_patient(db, ident)
    consent = generate_consent(); save_consent(db, pid, consent["notice"], consent)
    print("\nConsent captured. Let's begin triage. Type 'done' to finish.\n")
    history = []
    while True:
        msg = input("You: ")
        if msg.lower() == "done": break
        history.append({"role":"user","parts":[msg]})
        out = start_triage(history)
        print("AI:", out.get("questions_next", ["(no question)"])[0])
    print("\nA human doctor will review your case and follow up. Stay well!")

if __name__ == "__main__":
    run_cli()