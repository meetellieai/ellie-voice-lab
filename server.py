qxximport json
import re
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from lead_extractor import extract_lead_from_text
from n8n_client import send_lead_to_n8n


BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
CONFIG_EXAMPLE_PATH = BASE_DIR / "config.example.json"
RESULTS_DIR = BASE_DIR / "results"
RESULTS_PATH = RESULTS_DIR / "test_calls.json"
CALLER_MEMORY_PATH = RESULTS_DIR / "caller_memory.json"

app = FastAPI(title="Ellie Voice Lab")


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

    result = {
        "provider": "vogent",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "raw_payload": payload,
        "transcript": transcript,
        "lead": lead,
        "is_repeat_caller": is_repeat,
        "caller_memory": caller_memory,
        "memory_summary": memory_summary,
    }

    save_result(result)

    # Update caller memory
    update_caller_memory(lead)

    await send_lead_to_n8n(config.get("n8n_webhook_url", ""), result)

    return {"ok": True, "lead": lead, "is_repeat_caller": is_repeat, "memory_summary": memory_summary}


@app.post("/webhooks/test")
async def test_webhook(request: Request):
    payload = await request.json()

    transcript = payload.get("transcript", "")
    lead = extract_lead_from_text(transcript)

    # Check for repeat caller
    caller_memory = get_caller_by_phone(lead.get("phone"))
    is_repeat = bool(caller_memory)
    memory_summary = caller_memory.get("last_summary", "") if caller_memory else ""

    result = {
        "provider": "test",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "raw_payload": payload,
        "transcript": transcript,
        "lead": lead,
        "is_repeat_caller": is_repeat,
        "caller_memory": caller_memory,
        "memory_summary": memory_summary,
    }

    save_result(result)

    # Update caller memory
    update_caller_memory(lead)

    return {"ok": True, "lead": lead, "is_repeat_caller": is_repeat, "memory_summary": memory_summary}
