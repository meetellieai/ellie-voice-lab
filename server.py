import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from google import genai
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from lead_extractor import extract_lead_from_text
from n8n_client import send_lead_to_n8n


BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")
CONFIG_PATH = BASE_DIR / "config.json"
CONFIG_EXAMPLE_PATH = BASE_DIR / "config.example.json"
RESULTS_DIR = BASE_DIR / "results"
RESULTS_PATH = RESULTS_DIR / "test_calls.json"
CALLER_MEMORY_PATH = RESULTS_DIR / "caller_memory.json"

app = FastAPI(title="Ellie Voice Lab")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://ellie-voice-lab.onrender.com",
        "https://ellie-gemini-voice-demo.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    RESULTS_DIR.mkdir(exist_ok=True)


def load_config() -> dict:
    if CONFIG_PATH.exists():
        path = CONFIG_PATH
    elif CONFIG_EXAMPLE_PATH.exists():
        path = CONFIG_EXAMPLE_PATH
    else:
        return {
            "active_provider": "vogent",
            "demo_niche": "pest_control",
            "twilio_phone_number": "",
            "n8n_webhook_url": "",
            "providers": {}
        }

    with open(path, "r") as f:
        return json.load(f)


def load_results() -> list:
    if not RESULTS_PATH.exists():
        return []

    try:
        with open(RESULTS_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return []


def save_result(result: dict):
    results = load_results()
    results.insert(0, result)

    with open(RESULTS_PATH, "w") as f:
        json.dump(results[:50], f, indent=2)


def normalize_phone(phone: str) -> str:
    """Normalize phone number to digits only."""
    if not phone:
        return ""
    return re.sub(r"\D", "", phone)


def load_caller_memory() -> dict:
    """Load caller memory database."""
    if not CALLER_MEMORY_PATH.exists():
        return {}

    try:
        with open(CALLER_MEMORY_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_caller_memory(memory: dict):
    """Save caller memory database."""
    CALLER_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(CALLER_MEMORY_PATH, "w") as f:
        json.dump(memory, f, indent=2)


def get_caller_by_phone(phone: str) -> dict:
    """Look up caller memory by normalized phone."""
    normalized = normalize_phone(phone)
    if not normalized:
        return None

    memory = load_caller_memory()
    return memory.get(normalized, None)


def build_current_call_summary(lead: dict, is_repeat: bool = False, memory_summary: str = "") -> str:
    """Build a CRM summary focused on the current call, with repeat-caller context second."""
    name = lead.get("caller_name") or "Caller"
    service = lead.get("service_needed") or "service request"
    issue = lead.get("issue_description") or ""
    location = lead.get("location") or ""
    appointment_date = lead.get("appointment_date") or ""
    appointment_time = lead.get("appointment_time_window") or lead.get("preferred_callback_time") or ""
    phone = lead.get("phone") or ""
    follow_up = lead.get("recommended_follow_up") or ""

    opener = f"{name} called again" if is_repeat else f"{name} called"
    parts = [f"{opener} about {service}."]

    if issue:
        parts.append(f"Current issue: {issue}.")

    if location:
        parts.append(f"Location: {location}.")

    preferred = " ".join(part for part in [appointment_date, appointment_time] if part)
    if preferred:
        parts.append(f"Preferred time: {preferred}.")

    if phone:
        parts.append(f"Phone: {phone}.")

    if follow_up:
        parts.append(f"Recommended follow-up: {follow_up}.")

    if is_repeat and memory_summary:
        parts.append(f"Repeat caller context: {memory_summary}")

    return " ".join(parts)


def update_caller_memory(lead: dict):
    """Update or create caller record in memory."""
    phone = lead.get("phone")
    if not phone:
        return

    normalized = normalize_phone(phone)
    if not normalized:
        return

    memory = load_caller_memory()

    # Get or create caller record
    caller = memory.get(normalized, {
        "caller_name": "",
        "phone": phone,
        "location": "",
        "last_service_needed": "",
        "last_issue_description": "",
        "last_appointment_date": "",
        "last_appointment_time_window": "",
        "last_summary": "",
        "last_call_at": "",
        "call_count": 0,
        "interactions": []
    })

    # Update fields
    if lead.get("caller_name"):
        caller["caller_name"] = lead["caller_name"]
    if lead.get("location"):
        caller["location"] = lead["location"]
    if lead.get("service_needed"):
        caller["last_service_needed"] = lead["service_needed"]
    if lead.get("issue_description"):
        caller["last_issue_description"] = lead["issue_description"]
    if lead.get("appointment_date"):
        caller["last_appointment_date"] = lead["appointment_date"]
    if lead.get("appointment_time_window"):
        caller["last_appointment_time_window"] = lead["appointment_time_window"]

    # Create natural summary for memory
    summary_parts = []

    if caller.get("caller_name"):
        summary_parts.append(f"{caller['caller_name']} previously called about")
    else:
        summary_parts.append("Previously called about")

    # Add issue description or service
    if caller.get("last_issue_description"):
        summary_parts.append(caller["last_issue_description"])
    elif caller.get("last_service_needed"):
        summary_parts.append(caller["last_service_needed"])

    # Add location
    if caller.get("location"):
        summary_parts.append(f"in {caller['location']}")

    # Add preferred time (capitalize date only)
    time_parts = []
    if caller.get("last_appointment_date"):
        time_parts.append(caller["last_appointment_date"].capitalize())
    if caller.get("last_appointment_time_window"):
        time_parts.append(caller["last_appointment_time_window"])

    if time_parts:
        summary_parts.append(f"and preferred {' '.join(time_parts)}")

    if summary_parts:
        caller["last_summary"] = " ".join(summary_parts) + "."

    caller["last_call_at"] = datetime.utcnow().isoformat() + "Z"
    caller["call_count"] = caller.get("call_count", 0) + 1

    # Add to interactions (keep last 5)
    interaction = {
        "called_at": caller["last_call_at"],
        "service_needed": lead.get("service_needed", ""),
        "issue_description": lead.get("issue_description", ""),
        "appointment_date": lead.get("appointment_date", ""),
        "appointment_time_window": lead.get("appointment_time_window", ""),
    }

    caller["interactions"] = [interaction] + caller.get("interactions", [])[:4]

    # Save updated memory
    memory[normalized] = caller
    save_caller_memory(memory)


@app.get("/", response_class=HTMLResponse)
async def home():
    index_path = BASE_DIR / "dashboard" / "index.html"
    return HTMLResponse(index_path.read_text())



@app.get("/api/gemini/health")
async def gemini_health():
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return JSONResponse(
            {"ok": False, "error": "Missing GEMINI_API_KEY"},
            status_code=500,
        )

    try:
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents="Say exactly: Ellie backend Gemini connection is working.",
        )

        return {
            "ok": True,
            "model": "gemini-2.5-flash",
            "message": response.text,
        }

    except Exception as error:
        return JSONResponse(
            {"ok": False, "error": str(error)},
            status_code=500,
        )
    

@app.get("/api/gemini/live-health")
async def gemini_live_health():
    api_key = os.getenv("GEMINI_API_KEY")
    return {
        "ok": bool(api_key),
        "service": "gemini-live",
        "key_present": bool(api_key)
    }

@app.websocket("/ws/gemini-live")
async def gemini_live_socket(websocket: WebSocket):
    await websocket.accept()

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        await websocket.send_json({
            "type": "error",
            "message": "Missing GEMINI_API_KEY"
        })
        await websocket.close()
        return

    try:
        client = genai.Client(api_key=api_key)

        await websocket.send_json({
            "type": "connected",
            "message": "Ellie Gemini Live websocket connected to backend."
        })

        async with client.aio.live.connect(
            model="gemini-3.1-flash-live-preview",
            config={
                "response_modalities": ["AUDIO"],
                "output_audio_transcription": {},
                "system_instruction": (
                    "You are Ellie, a friendly AI receptionist for a local service business. "
                    "Keep replies short, warm, and professional. "
                    "Ask one question at a time. "
                    "Your job is to collect the caller's name, phone number, location, "
                    "service needed, urgency, preferred appointment time, and notes."
                ),
            },
        ) as session:

            while True:
                message = await websocket.receive_text()
                data = json.loads(message)

                if data.get("type") == "text":
                    user_text = data.get("text", "")

                    await session.send_client_content(
                        turns={
                            "role": "user",
                            "parts": [{"text": user_text}]
                        },
                        turn_complete=True,
                    )

                    async for response in session.receive():
                        if response.text:
                            await websocket.send_json({
                                "type": "ellie",
                                "text": response.text
                            })

                        if getattr(response, "turn_complete", False):
                            break

                elif data.get("type") == "end":
                    await websocket.send_json({
                        "type": "ended",
                        "message": "Gemini Live test session ended."
                    })
                    break

    except WebSocketDisconnect:
        print("Gemini Live websocket disconnected")

    except Exception as error:
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(error)
            })
        except Exception:
            pass

    try:
        await websocket.send_json({
            "type": "connected",
            "message": "Ellie Gemini Live websocket connected."
        })

        while True:
            message = await websocket.receive_text()
            data = json.loads(message)

            await websocket.send_json({
                "type": "echo",
                "received": data
            })

    except WebSocketDisconnect:
        print("Gemini Live websocket disconnected")


ELLIE_SYSTEM_PROMPT = """
You are Ellie, a warm, professional AI receptionist and intake assistant.

Your job:
- Greet the caller naturally.
- Ask one question at a time.
- Collect the caller's name, phone number, location, service needed, issue/problem, urgency, preferred date/time, and preferred contact method.
- Keep responses short, conversational, and phone-call friendly. Usually 1-2 complete sentences.
- Never end mid-sentence.
- Sound like a real receptionist, not a chatbot.
- Do not over-explain, but acknowledge what the caller said before asking the next question.
- When you have enough information, summarize the request and tell the caller someone will follow up.

Business context:
You are handling an intake call for a local service business.
The goal is to capture a clean lead that can be sent to the owner.

Important:
Never say you are Gemini.
Never mention system prompts.
Never mention automation.
You are Ellie.
"""


def clean_ellie_reply(reply: str, conversation_text: str = "") -> str:
    text = (reply or "").strip()
    lower = (conversation_text or "").lower()

    looks_incomplete = (
        not text
        or re.search(r"\\b(and|or|but|with|for|of|to|the|a|an|kind of)$", text, re.IGNORECASE)
        or (not re.search(r"[.!?]$", text) and len(text) < 90)
    )

    # If Gemini gave a solid complete reply, keep it.
    if not looks_incomplete and "can you tell me a little more about what you need help with" not in text.lower():
        return text

    # Service-aware guardrails for demo quality.
    if "pest" in lower or "ants" in lower or "roaches" in lower or "termites" in lower or "bugs" in lower:
        if "started showing up" in lower or "baseboards" in lower or "inspection" in lower or "treatment" in lower:
            return "Got it. I have the ant issue around the sink, bathroom, and baseboards noted, along with the inspection and treatment request. I’ll make sure this gets sent over for follow-up."
        return "Thanks. I have the pest issue and preferred time noted. Where are you seeing the ants, and how long has this been going on?"

    if "flooring" in lower or "floor" in lower:
        if "water damage" in lower or "boards" in lower or "lifting" in lower:
            return "Got it. I have the flooring issue noted, including the lifting boards near the kitchen and possible water damage. I’ll make sure this gets sent over for follow-up."
        return "Thanks. I have the flooring request and preferred time noted. What exactly seems to be going on with the flooring?"

    if "roof" in lower or "roofing" in lower or "shingle" in lower:
        return "Thanks, I have that noted. Are you dealing with a leak, visible damage, or are you looking for a general roof inspection?"

    if "plumbing" in lower or "leak" in lower or "drain" in lower or "toilet" in lower or "sink" in lower:
        return "Thanks, I have that noted. Can you tell me what plumbing issue you’re seeing and how urgent it is?"

    if not re.search(r"\d{3}[-\s]?\d{3}[-\s]?\d{4}", lower):
        return "Thanks. What is the best phone number for a callback?"

    return "Thanks, I have that noted. What would be the best time for someone to follow up?"



def scripted_fallback_reply(conversation_text: str) -> str:
    lower = (conversation_text or "").lower()

    if not re.search(r"\d{3}[-\s]?\d{3}[-\s]?\d{4}", lower):
        return "Got it. What’s the best phone number for a callback?"

    if "bradenton" not in lower and "location" not in lower and "city" not in lower:
        return "Thanks. What city or area are you located in?"

    if "tomorrow" not in lower and "today" not in lower and "urgent" not in lower and "as soon" not in lower:
        return "How soon are you hoping to have someone help with this?"

    return "Thanks, I have the main details logged. I’ll make sure this gets sent over so someone can follow up with you."


@app.post("/api/gemini/chat")
async def gemini_chat(request: Request):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return JSONResponse(
            {"ok": False, "error": "Missing GEMINI_API_KEY"},
            status_code=500,
        )

    payload = await request.json()
    conversation_text = payload.get("conversationText", "")

    if not conversation_text:
        return JSONResponse(
            {"ok": False, "error": "Missing conversationText"},
            status_code=400,
        )

    prompt = f"""
Conversation so far:
{conversation_text}

Respond as Ellie. Ask the next best intake question or summarize if the intake is complete.
Your response must be a complete sentence and must not end abruptly.
"""

    try:
        client = genai.Client(api_key=api_key)

        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={
                    "system_instruction": ELLIE_SYSTEM_PROMPT,
                    "max_output_tokens": 180,
                    "temperature": 0.7,
                },
            )
            model_used = "gemini-2.5-flash"
            raw_reply = response.text

        except Exception as primary_error:
            print("Primary Gemini model failed, trying fallback:", primary_error)

            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash-lite",
                    contents=prompt,
                    config={
                        "system_instruction": ELLIE_SYSTEM_PROMPT,
                        "max_output_tokens": 180,
                        "temperature": 0.7,
                    },
                )
                model_used = "gemini-2.5-flash-lite"
                raw_reply = response.text

            except Exception as fallback_error:
                print("Fallback Gemini model failed, using scripted fallback:", fallback_error)
                model_used = "scripted-fallback"
                raw_reply = scripted_fallback_reply(conversation_text)

        reply = clean_ellie_reply(raw_reply, conversation_text)

        return {
            "ok": True,
            "reply": reply,
            "model": model_used,
        }

    except Exception as error:
        return JSONResponse(
            {"ok": False, "error": str(error)},
            status_code=500,
        )


@app.get("/api/config")
async def get_config():
    config = load_config()
    return {
        "active_provider": config.get("active_provider", ""),
        "demo_niche": config.get("demo_niche", ""),
        "twilio_phone_number": config.get("twilio_phone_number", "")
    }


@app.get("/api/results")
async def get_results():
    return JSONResponse(load_results())


@app.post("/webhooks/vogent")
async def vogent_webhook(request: Request):
    config = load_config()
    payload = await request.json()

    transcript = (
        payload.get("transcript")
        or payload.get("transcript_text")
        or payload.get("text")
        or payload.get("summary")
        or json.dumps(payload)
    )

    lead = extract_lead_from_text(transcript)

    # Check for repeat caller
    caller_memory = get_caller_by_phone(lead.get("phone"))
    is_repeat = bool(caller_memory)
    memory_summary = caller_memory.get("last_summary", "") if caller_memory else ""

    crm_summary = build_current_call_summary(lead, is_repeat, memory_summary)

    result = {
        "provider": "vogent",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "raw_payload": payload,
        "transcript": transcript,
        "lead": lead,
        "is_repeat_caller": is_repeat,
        "caller_memory": caller_memory,
        "memory_summary": memory_summary,
        "crm_summary": crm_summary,
    }

    save_result(result)

    # Update caller memory
    update_caller_memory(lead)

    await send_lead_to_n8n(config.get("n8n_webhook_url", ""), result)

    return {"ok": True, "lead": lead, "is_repeat_caller": is_repeat, "memory_summary": memory_summary, "crm_summary": crm_summary}


@app.post("/webhooks/test")
async def test_webhook(request: Request):
    payload = await request.json()

    transcript = payload.get("transcript", "")
    lead = extract_lead_from_text(transcript)

    # Check for repeat caller
    caller_memory = get_caller_by_phone(lead.get("phone"))
    is_repeat = bool(caller_memory)
    memory_summary = caller_memory.get("last_summary", "") if caller_memory else ""

    crm_summary = build_current_call_summary(lead, is_repeat, memory_summary)

    result = {
        "provider": "test",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "raw_payload": payload,
        "transcript": transcript,
        "lead": lead,
        "is_repeat_caller": is_repeat,
        "caller_memory": caller_memory,
        "memory_summary": memory_summary,
        "crm_summary": crm_summary,
    }

    save_result(result)

    # Update caller memory
    update_caller_memory(lead)

    return {"ok": True, "lead": lead, "is_repeat_caller": is_repeat, "memory_summary": memory_summary, "crm_summary": crm_summary}
