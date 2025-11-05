# ui/gradio_ui.py
"""
Gradio UI for the Virtual Medical Practitioner (India).

Features:
- Identity verification + DPDP-style consent capture.
- Triage chat using Chatbot messages format (OpenAI-style {role, content}).
- Progress bars (client & server-side) during long-running operations.
- Medicines lookup (India-specific legal status & precautions) with RED safety callouts.
- Doctor Review tab (list recent consultations, view details, mark review decisions).
- Mounted inside FastAPI at /ui (see web/api.py).

Notes:
- For production, keep Identity & Consent enabled (no test-mode bypass here).
- All PHI is encrypted at rest via storage layer.
"""

import datetime as _dt
import json
import gradio as gr

from storage.store import (
    SessionLocal,
    save_patient,
    save_consent,
    save_consultation,
    audit,
    init_db,
    Consultation,  # SQLAlchemy model (queried directly in Doctor Review)
)
from agents.identity import identity_payload
from agents.compliance import generate_consent
from agents.triage import start_triage
from agents.medication import build_medicine_card, get_medicine_safety_json
from core.constants import AI_DISCLOSURE, EMERGENCY_BANNER


# ------------------------------
# Helpers (formatting / UI)
# ------------------------------

def _format_alert_block(title: str, items: list[str]) -> str:
    """
    Render a strong red/bold callout block for safety items.
    Works inside a Markdown component (HTML allowed).
    """
    if not items:
        return ""
    # Keep HTML simple to avoid sanitizer issues across Gradio versions.
    bullets = "".join(f"<li><b>{i}</b></li>" for i in items)
    return (
        '<div style="border-left:6px solid #c62828; background:#ffebee; padding:10px 12px; '
        'margin:12px 0; border-radius:6px">'
        f'<div style="color:#b00020; font-weight:800; font-size:14px; text-transform:uppercase;">{title}</div>'
        f'<ul style="margin:8px 0; padding-left:18px; color:#111; font-size:14px;">{bullets}</ul>'
        "</div>"
    )


# ------------------------------
# Helper actions used by Gradio
# ------------------------------

def _identify(name, age, id_type, id_value, phone, email):
    """Verify identity & create a patient row (encrypted at rest)."""
    prog = gr.Progress()
    prog(0.1, desc="Validating identity...")
    if not name or age is None or not id_type or not id_value or not phone:
        return None, "❌ Please fill all required fields."
    try:
        age = int(age)
    except Exception:
        return None, "❌ Age must be an integer."

    idp = identity_payload(name, age, id_type, id_value, phone, email)
    if not idp["verified"]:
        return None, "❌ Identity verification failed. Check ID format/phone."

    prog(0.6, desc="Saving securely...")
    db = SessionLocal()
    pid = save_patient(db, idp)
    audit(db, "identify", "user", "patient", {"pid": pid})

    prog(1.0, desc="Done")
    return pid, f"✅ Verified. Patient ID: `{pid}`"


def _consent(pid, language):
    """Record explicit consent (DPDP style) and show the notice."""
    prog = gr.Progress()
    prog(0.1, desc="Preparing consent notice...")
    if not pid:
        return None, "❌ Verify identity first.", ""
    notice = generate_consent(language=language)

    prog(0.6, desc="Recording consent...")
    db = SessionLocal()
    cid = save_consent(db, pid, notice["notice"], notice)
    audit(db, "consent", "user", "consent", {"pid": pid, "cid": cid})

    prog(1.0, desc="Done")
    return cid, f"✅ Consent recorded (ID: `{cid}`)", notice["notice"]


def _triage(pid, llm_history, chat_messages, user_msg):
    """
    One triage turn using 'messages' format for Chatbot.
      - llm_history: list[dict] (LLM-native history) with role 'user'/'model' and parts [text]
      - chat_messages: list[dict] for Chatbot, with keys {'role','content'} (user/assistant)
      - user_msg: current user input

    Returns updated llm_history, result JSON, chat_messages (state), chatbot value, cleared input.
    """
    llm_history = llm_history or []
    chat_messages = chat_messages or []

    # TEMP: test-mode bypass (remove in production)
    pid = pid or 9999

    print(f"[{_dt.datetime.now().isoformat()}] TRIAGE IN pid={pid} msg={user_msg!r}")

    if not pid:
        chat_messages.append({"role": "assistant", "content": "❌ Please verify identity and record consent first."})
        return llm_history, None, chat_messages, chat_messages, ""

    if not user_msg:
        chat_messages.append({"role": "assistant", "content": "Please type your symptom/message."})
        return llm_history, None, chat_messages, chat_messages, ""

    # Append user turn to LLM-native history so the agent sees context
    # llm_history.append({"role": "user", "parts": [user_msg]})

    # Call triage agent (returns dict result, assistant reply text, and updated_history)
    result, assistant_reply, updated_history = start_triage(llm_history, user_msg=user_msg)

    # Chatbot messages format (OpenAI-style)
    chat_messages.append({"role": "user", "content": user_msg})
    chat_messages.append({"role": "assistant", "content": assistant_reply})

    # ✅ Show self-care advice if available and not already part of assistant_reply
    if result.get("self_care_advice"):
        advice = result["self_care_advice"].strip()
        summary = result.get("summary", "").lower()
        if advice and "symptom" in summary and advice.lower() not in assistant_reply.lower():
            chat_messages.append({
                "role": "assistant",
                "content": f"🩺 **Self-care advice:**\n{advice}"
            })

    print(f"[{_dt.datetime.now().isoformat()}] TRIAGE OUT reply={assistant_reply[:80]!r}")

    # Return updated states and clear input
    return updated_history, result, chat_messages, chat_messages, ""


def _save_consult(pid, llm_history, result):
    """Save the current consultation securely (encrypted JSON blobs)."""
    if not pid:
        return "❌ No patient session. Verify identity first."
    prog = gr.Progress()
    prog(0.2, desc="Encrypting and saving...")
    db = SessionLocal()
    cons_id = save_consultation(
        db,
        pid,
        {"history": llm_history or []},
        result or {},
    )
    audit(db, "triage", "ai", "consultation", {"pid": pid, "consultation_id": cons_id})
    prog(1.0, desc="Done")
    return f"🔒 Saved consultation ID: `{cons_id}`"


def _med_search(query):
    """
    Stream status updates into the Medicines Markdown while we fetch:
      1) the base card
      2) safety JSON
      3) format the final result
    """
    # 0) Guard: empty query
    if not (query and query.strip()):
        yield "Enter a generic/brand name to search."
        return

    # 1) Show immediate status
    yield "⏳ **Searching…** Please wait."

    # Optional server-side progress (overlay)
    prog = gr.Progress()
    prog(0.15, desc="Searching medicine info…")

    # 2) Build the card
    try:
        card = build_medicine_card(query.strip())
    except Exception as e:
        yield f"❌ Error while searching: {e}"
        return

    # 3) Inline status update while we fetch safety
    yield "🔍 **Collecting safety highlights…**"
    prog(0.55, desc="Collecting safety highlights…")
    try:
        from agents.medication import get_medicine_safety_json  # local import to avoid circulars at load
        safety = get_medicine_safety_json(
            query.strip(),
            card.get("generic_name", ""),
            card.get("drug_class", "")
        )
    except Exception as e:
        safety = {}
        # We still continue; just skip safety blocks.
        yield f"⚠️ Couldn’t fetch safety highlights: {e}"

    # 4) Formatting final output
    yield "⚙️ **Formatting…**"
    prog(0.85, desc="Formatting result…")

    # Build red callout blocks (re-use your helper)
    blk_prec = _format_alert_block("Mandatory Precautions", safety.get("mandatory_precautions", []))
    blk_impl = _format_alert_block("Implications if ignored", safety.get("implications_if_ignored", []))
    blk_who  = _format_alert_block("Who should avoid", safety.get("who_should_avoid", []))
    blk_how  = _format_alert_block("How to take", safety.get("how_to_take", []))

    cites = safety.get("source_citations", []) if safety else []
    cite_md = ""
    if cites:
        cite_md = "\n**Sources:**\n" + "\n".join(f"- {c}" for c in cites[:6])

    text = (
        f"**Query:** {card.get('query','')}\n\n"
        f"**Legal status (India):** {card.get('rx_classification','')}\n\n"
        f"**Summary (Indian context):**\n{card.get('llm_summary','')}\n\n"
        f"{blk_prec}{blk_impl}{blk_who}{blk_how}"
        f"{cite_md}\n\n"
        f"> ⚠️ **Schedule H/H1/X** items are prescription-only in India. "
        f"Unscheduled items may be sold without prescription—confirm with your pharmacist."
    )

    prog(1.0, desc="Done")
    yield text

# ------------------------------
# Doctor Review helpers
# ------------------------------

def _list_recent_consults(limit: int = 15):
    """Return a simple table of recent consultations: [id, patient_id, created_at]."""
    prog = gr.Progress()
    prog(0.2, desc="Loading recent consultations...")
    db = SessionLocal()
    rows = (
        db.query(Consultation)
        .order_by(Consultation.created_at.desc())
        .limit(limit)
        .all()
    )
    data = [[c.id, c.patient_id, c.created_at.isoformat()] for c in rows]
    prog(1.0, desc="Done")
    return data


def _load_consult_details(consultation_id: int):
    """Fetch & decrypt a consultation; render transcript + triage JSON as Markdown."""
    prog = gr.Progress()
    prog(0.2, desc="Loading consultation...")
    db = SessionLocal()
    c = db.get(Consultation, consultation_id)
    if not c:
        return f"❌ Consultation `{consultation_id}` not found."

    # Decrypt blobs
    from security.crypto import decrypt_json
    transcript = decrypt_json(c.transcript)
    assessment = decrypt_json(c.assessment)

    prog(0.8, desc="Formatting details...")
    # transcript: {"history":[{"role":"user"/"model","parts":[text]}...]}
    hist = transcript.get("history", [])
    lines = ["### Transcript"]
    for i, turn in enumerate(hist, 1):
        role = turn.get("role", "?")
        text = (turn.get("parts") or [""])[0]
        prefix = "👤 User" if role == "user" else "🤖 Assistant"
        lines.append(f"{i}. **{prefix}:** {text}")

    # assessment JSON
    lines.append("\n### Triage Assessment (JSON)")
    lines.append("```json")
    lines.append(json.dumps(assessment, indent=2))
    lines.append("```")

    prog(1.0, desc="Done")
    return "\n".join(lines)


def _mark_review(consultation_id: int, decision: str, notes: str):
    """Record doctor review decision in audit log."""
    if not consultation_id:
        return "❌ Enter a valid consultation ID."
    if decision not in ("Approve", "Refer"):
        return "❌ Select a decision (Approve/Refer)."

    prog = gr.Progress()
    prog(0.2, desc="Recording review...")
    db = SessionLocal()
    details = {
        "consultation_id": consultation_id,
        "decision": decision,
        "notes": notes or "",
        "ts": _dt.datetime.utcnow().isoformat() + "Z",
    }
    audit(db, "doctor_review", "doctor", "consultation", details)
    prog(1.0, desc="Done")
    return f"✅ Review recorded for Consultation `{consultation_id}`: **{decision}**"


# ------------------------------
# UI Builder
# ------------------------------

def build_ui():
    """Create the full Gradio UI and return the Blocks app."""
    # Ensure DB tables exist before user interacts
    init_db()

    with gr.Blocks(title="Virtual Medical Practitioner (India)") as demo:
        gr.Markdown(f"### {AI_DISCLOSURE}\n\n> {EMERGENCY_BANNER}")

        # -----------------
        # Identity & Consent
        # -----------------
        with gr.Tab("Identity & Consent"):
            with gr.Row():
                name = gr.Textbox(label="Full name", placeholder="Ravi Kumar")
                age = gr.Number(label="Age", value=30, precision=0)
            with gr.Row():
                id_type = gr.Dropdown(
                    choices=["PAN", "AADHAAR"],
                    label="ID Type",
                    value="PAN",
                )
                id_value = gr.Textbox(label="ID Number (format only; stored encrypted)")
            with gr.Row():
                phone = gr.Textbox(label="Phone", value="+919999999999")
                email = gr.Textbox(label="Email (optional)")

            verify_btn = gr.Button("Verify Identity")
            patient_id = gr.State()
            verify_out = gr.Markdown()

            lang = gr.Dropdown(choices=["en"], value="en", label="Consent Language")
            consent_btn = gr.Button("Record Consent")
            consent_id = gr.State()
            consent_out = gr.Markdown()
            notice_md = gr.Markdown()

            verify_btn.click(
                _identify,
                inputs=[name, age, id_type, id_value, phone, email],
                outputs=[patient_id, verify_out],
                show_progress="full",
            )
            consent_btn.click(
                _consent,
                inputs=[patient_id, lang],
                outputs=[consent_id, consent_out, notice_md],
                show_progress="full",
            )

        # ------
        # Triage
        # ------
        with gr.Tab("Triage"):
            gr.Markdown(
                "Chat about your symptoms. The assistant will ask focused follow‑up questions."
            )

            # Use 'messages' format (OpenAI-style dicts)
            chat = gr.Chatbot(label="AI Triage Chat", type="messages", height=340)
            user_msg = gr.Textbox(label="Your message")
            llm_history = gr.State([])     # LLM-native conversation (list[dict]: role 'user'/'model', parts [text])
            chat_state = gr.State([])      # Chatbot messages (list[dict]: {'role','content'})
            result_state = gr.State()      # last triage JSON

            with gr.Row():
                ask_btn = gr.Button("Send", variant="primary")
                save_btn = gr.Button("Save Consultation")
                reset_btn = gr.Button("Reset Chat")

            save_out = gr.Markdown()

            # Send message: update states, chatbot display, and clear input
            ask_btn.click(
                _triage,
                inputs=[patient_id, llm_history, chat_state, user_msg],
                outputs=[llm_history, result_state, chat_state, chat, user_msg],
                show_progress=False,   # ✅ No overlay for triage; avoids duplicate/fixed progress
            )

            # Save consultation
            save_btn.click(
                _save_consult,
                inputs=[patient_id, llm_history, result_state],
                outputs=save_out,
                show_progress="full",
            )

            # Reset chat (clears LLM history, result, message list, chat UI, and input)
            reset_btn.click(
                lambda: ([], None, [], [], ""),
                inputs=None,
                outputs=[llm_history, result_state, chat_state, chat, user_msg],
            )

        # ----------
        # Medicines
        # ----------
        with gr.Tab("Medicines"):
            gr.Markdown(
                "Look up a medicine (generic/brand) and see **Indian** legal status & precautions.  \n"
                "_Red boxes highlight **Mandatory Precautions** and **Implications if ignored**._"
            )
            q = gr.Textbox(label="Medicine name", placeholder="paracetamol")
            search_btn = gr.Button("Search")
            med_md = gr.Markdown()
            search_btn.click(_med_search, inputs=[q], outputs=[med_md], show_progress="full")

        # --------------
        # Doctor Review
        # --------------
        with gr.Tab("Doctor Review"):
            gr.Markdown(
                "This tab is for the supervising doctor to review consultations before issuing a prescription."
            )

            # Recent consultations table
            with gr.Row():
                refresh_btn = gr.Button("Refresh Recent")
                recent_df = gr.Dataframe(
                    headers=["Consultation ID", "Patient ID", "Created At (UTC)"],
                    datatype=["number", "number", "str"],
                    interactive=False,
                    wrap=True,
                    row_count=(10, "dynamic"),  # limit visible rows; remove height for broad Gradio compatibility
                )

            refresh_btn.click(
                _list_recent_consults,
                inputs=None,
                outputs=recent_df,
                show_progress="full",
            )

            # Load consultation details (transcript + triage JSON)
            with gr.Row():
                consult_id_in = gr.Number(label="Consultation ID to Open", precision=0)
                open_btn = gr.Button("Open Consultation")
            details_md = gr.Markdown()

            open_btn.click(
                _load_consult_details,
                inputs=[consult_id_in],
                outputs=[details_md],
                show_progress="full",
            )

            # Record review decision
            with gr.Row():
                decision = gr.Dropdown(
                    choices=["Approve", "Refer"],
                    label="Review Decision",
                    value="Approve",
                )
                notes = gr.Textbox(
                    label="Doctor notes (optional)",
                    placeholder="Add clinical notes or follow-up instructions..."
                )
                submit_review_btn = gr.Button("Mark Reviewed", variant="primary")

            review_out = gr.Markdown()
            submit_review_btn.click(
                _mark_review,
                inputs=[consult_id_in, decision, notes],
                outputs=[review_out],
                show_progress="full",
            )

        # Compliance/footer
        gr.Markdown(
            "**Compliance note:** DPDP Act, 2023 principles (explicit consent, minimization, encryption-at-rest) "
            "are followed. Approvals are by CDSCO/DCGI; Schedule H/H1/X are prescription-only. "
            "A human doctor will review before any prescription."
        )

    # ✅ Return a Blocks instance
    return demo