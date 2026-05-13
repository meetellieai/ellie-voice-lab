import re


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def strip_speaker_labels(text: str) -> str:
    text = text or ""
    text = re.sub(r"\b(Ellie|Caller)\s*:\s*", "", text, flags=re.IGNORECASE)
    return clean_text(text)


def extract_caller_name(text: str) -> str:
    """Extract caller name from Caller lines only, so Ellie is never mistaken as the caller."""
    caller_lines = []

    for line in (text or "").splitlines():
        if line.strip().lower().startswith("caller:"):
            caller_lines.append(re.sub(r"^caller\s*:\s*", "", line.strip(), flags=re.IGNORECASE))

    search_text = " ".join(caller_lines) if caller_lines else text

    patterns = [
        r"\bmy name is\s+([a-zA-Z][a-zA-Z'-]+)",
        r"\bthis is\s+([a-zA-Z][a-zA-Z'-]+)(?:\s|,|\.)",
        r"\bi'm\s+([a-zA-Z][a-zA-Z'-]+)(?:\s|,|\.)",
        r"\bi am\s+([a-zA-Z][a-zA-Z'-]+)(?:\s|,|\.)",
        r"\b([a-zA-Z][a-zA-Z'-]+)\s+speaking\b",
        r"\b(?:it's|it is)\s+([a-zA-Z][a-zA-Z'-]+)\b",
    ]

    bad_names = {"ellie", "just", "the", "a", "an", "ok", "yeah", "yes", "no", "calling", "looking"}

    for pattern in patterns:
        match = re.search(pattern, search_text, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            if name.lower() not in bad_names:
                return name.capitalize()

    return ""


def extract_phone(text: str) -> str:
    """Extract North American phone numbers in common formats."""
    match = re.search(
        r"(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}",
        text,
    )
    if match:
        return match.group(0).strip()
    return ""


def extract_location(text: str) -> str:
    """Extract city/location from common patterns and known Florida/local terms."""
    patterns = [
        r"\bi(?:'m| am)\s+in\s+([a-zA-Z\s'-]+?)(?:\.|,|\n|$)",
        r"\blocated in\s+([a-zA-Z\s'-]+?)(?:\.|,|\n|$)",
        r"\bwe(?:'re| are)\s+in\s+([a-zA-Z\s'-]+?)(?:\.|,|\n|$)",
        r"\bmy address is\s+(.+?)(?:\.|\n|$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            location = clean_text(match.group(1))
            location = re.sub(r"\b(and|but|so|because)\b.*$", "", location, flags=re.IGNORECASE).strip()
            if location:
                return location.title()

    known_locations = [
        "bradenton",
        "sarasota",
        "tampa",
        "st pete",
        "st. pete",
        "clearwater",
        "palmetto",
        "lakewood ranch",
        "anna maria",
        "longboat key",
    ]

    lower = text.lower()
    for location in known_locations:
        if location in lower:
            return location.title()

    return ""


def extract_service_needed(text: str) -> str:
    """Classify the service category from transcript."""
    lower = text.lower()

    service_map = {
        "flooring": [
            "flooring",
            "floor repair",
            "hardwood",
            "wood floor",
            "boards",
            "floor boards",
            "vinyl",
            "laminate",
            "tile",
            "carpet",
        ],
        "pest control": [
            "pest",
            "ants",
            "roaches",
            "cockroach",
            "termites",
            "bugs",
            "spiders",
            "rodent",
            "rats",
            "mice",
        ],
        "roofing": [
            "roof",
            "shingles",
            "leak in the roof",
            "roof repair",
        ],
        "plumbing": [
            "plumbing",
            "pipe",
            "toilet",
            "sink",
            "water leak",
            "drain",
            "faucet",
        ],
        "hvac": [
            "air conditioning",
            "ac ",
            "a/c",
            "hvac",
            "heater",
            "furnace",
            "thermostat",
        ],
    }

    for service, keywords in service_map.items():
        if any(keyword in lower for keyword in keywords):
            return service

    if "quote" in lower or "estimate" in lower:
        return "quote/estimate request"

    if "repair" in lower:
        return "repair"

    return ""


def extract_appointment_type(text: str) -> str:
    lower = text.lower()

    if "quote" in lower or "estimate" in lower:
        return "quote"
    if "inspection" in lower:
        return "inspection"
    if "consultation" in lower:
        return "consultation"
    if "appointment" in lower:
        return "appointment"
    if "service call" in lower:
        return "service call"
    if "callback" in lower or "call back" in lower:
        return "callback"

    return ""


def extract_appointment_date(text: str) -> str:
    lower = text.lower()

    ordered_patterns = [
        "today",
        "tomorrow",
        "this week",
        "next week",
        "next monday",
        "next tuesday",
        "next wednesday",
        "next thursday",
        "next friday",
        "next saturday",
        "next sunday",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ]

    for pattern in ordered_patterns:
        if pattern in lower:
            return pattern

    month_match = re.search(
        r"\b(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\s+(\d{1,2})\b",
        text,
        re.IGNORECASE,
    )
    if month_match:
        return f"{month_match.group(1).title()} {month_match.group(2)}"

    slash_match = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", text)
    if slash_match:
        return slash_match.group(0)

    return ""


def extract_appointment_time_window(text: str) -> str:
    lower = text.lower()

    time_windows = [
        "early morning",
        "late morning",
        "morning",
        "early afternoon",
        "late afternoon",
        "afternoon",
        "evening",
        "after work",
        "before noon",
        "after 5",
        "anytime",
    ]

    for window in time_windows:
        if window in lower:
            return window

    between_match = re.search(r"\bbetween\s+(\d{1,2})(?::\d{2})?\s*(am|pm)?\s+and\s+(\d{1,2})(?::\d{2})?\s*(am|pm)?\b", lower)
    if between_match:
        return between_match.group(0)

    range_match = re.search(r"\b(\d{1,2})(?::\d{2})?\s*(am|pm)?\s*(?:-|to)\s*(\d{1,2})(?::\d{2})?\s*(am|pm)\b", lower)
    if range_match:
        return range_match.group(0)

    exact_match = re.search(r"\b(?:around|at)?\s*(\d{1,2})(?::\d{2})?\s*(am|pm)\b", lower)
    if exact_match:
        return exact_match.group(0).strip()

    return ""


def extract_issue_description(text: str) -> str:
    """
    Extract a fuller issue description instead of returning only one keyword.
    Looks for the caller's own problem statement.
    """
    cleaned = strip_speaker_labels(text)

    patterns = [
        r"\bI need someone to\s+([^.!?]+)",
        r"\bI need\s+([^.!?]+)",
        r"\bI have\s+([^.!?]+)",
        r"\bI've got\s+([^.!?]+)",
        r"\bThere (?:are|is)\s+([^.!?]+)",
        r"\bThe issue is\s+([^.!?]+)",
        r"\bThe problem is\s+([^.!?]+)",
        r"\bI'm worried\s+([^.!?]+)",
    ]

    candidates = []

    for pattern in patterns:
        for match in re.finditer(pattern, cleaned, re.IGNORECASE):
            phrase = clean_text(match.group(1))
            if 8 <= len(phrase) <= 220:
                candidates.append(phrase)

    # Prefer the richest phrase that mentions a concrete issue.
    issue_words = [
        "lifting",
        "water damage",
        "damage",
        "broken",
        "leak",
        "repair",
        "quote",
        "estimate",
        "near",
        "kitchen",
        "bathroom",
        "boards",
        "floor",
        "pest",
        "ants",
        "roaches",
        "termites",
    ]

    scored = []
    for candidate in candidates:
        score = sum(1 for word in issue_words if word in candidate.lower())
        scored.append((score, len(candidate), candidate))

    if scored:
        scored.sort(reverse=True)
        best = scored[0][2]
        return best[0].upper() + best[1:] if best else ""

    # Keyword fallback, but return a helpful phrase instead of one word.
    lower = cleaned.lower()
    if "water damage" in lower:
        return "Possible water damage"
    if "boards" in lower and "lifting" in lower:
        return "Boards lifting"
    if "flooring repair" in lower:
        return "Flooring repair request"
    if "quote" in lower or "estimate" in lower:
        return "Quote/estimate request"

    return ""


def extract_urgency(text: str) -> str:
    lower = text.lower()

    if any(word in lower for word in ["emergency", "urgent", "asap", "as soon as possible", "right away", "immediately"]):
        return "urgent"

    if "today" in lower:
        return "today"

    if "tomorrow" in lower:
        return "tomorrow"

    if "this week" in lower:
        return "this week"

    if "next week" in lower:
        return "next week"

    return ""


def extract_preferred_contact_method(text: str) -> str:
    lower = text.lower()

    if any(word in lower for word in ["text me", "text is best", "sms"]):
        return "text"
    if any(word in lower for word in ["email me", "email is best", "e-mail"]):
        return "email"
    if any(word in lower for word in ["call me", "phone call", "call is best"]):
        return "call"

    return ""


def extract_special_requests(text: str) -> str:
    lower = text.lower()

    request_keywords = [
        "after hours",
        "weekend",
        "gate code",
        "dogs",
        "dog",
        "pets",
        "no pets",
        "kids present",
        "elderly",
        "allergy",
        "wheelchair",
        "accessible",
    ]

    found = [word for word in request_keywords if word in lower]
    return "; ".join(found)


def build_summary(lead: dict) -> str:
    parts = []

    if lead.get("caller_name"):
        parts.append(f"{lead['caller_name']} called")
    else:
        parts.append("Caller reached out")

    if lead.get("service_needed"):
        parts.append(f"about {lead['service_needed']}")

    if lead.get("issue_description"):
        parts.append(f"issue: {lead['issue_description']}")

    if lead.get("location"):
        parts.append(f"location: {lead['location']}")

    if lead.get("appointment_date") or lead.get("appointment_time_window"):
        preferred = " ".join(
            part for part in [lead.get("appointment_date"), lead.get("appointment_time_window")] if part
        )
        parts.append(f"preferred time: {preferred}")

    if lead.get("phone"):
        parts.append(f"phone: {lead['phone']}")

    return ". ".join(parts) + "."


def determine_appointment_readiness(lead: dict) -> str:
    has_name = bool(lead.get("caller_name"))
    has_phone = bool(lead.get("phone"))
    has_service = bool(lead.get("service_needed") or lead.get("issue_description"))
    has_time = bool(lead.get("appointment_time_window") or lead.get("appointment_date") or lead.get("preferred_callback_time"))

    if has_name and has_phone and has_service and has_time:
        return "Ready"
    if has_phone and has_service:
        return "Needs Follow-up"
    return "Incomplete"


def extract_lead_from_text(text: str) -> dict:
    """
    Extract lead information from call transcript.
    Designed for simple service-business intake demos.
    """
    text = text or ""
    cleaned = clean_text(text)

    appointment_date = extract_appointment_date(cleaned)
    appointment_time = extract_appointment_time_window(cleaned)

    lead = {
        "caller_name": extract_caller_name(cleaned),
        "phone": extract_phone(cleaned),
        "location": extract_location(cleaned),
        "service_needed": extract_service_needed(cleaned),
        "urgency": extract_urgency(cleaned),
        "preferred_callback_time": appointment_time,
        "notes": cleaned[:1200],
        "lead_quality": "Unknown",
        "appointment_type": extract_appointment_type(cleaned),
        "appointment_date": appointment_date,
        "appointment_time_window": appointment_time,
        "issue_description": extract_issue_description(cleaned),
        "preferred_contact_method": extract_preferred_contact_method(cleaned),
        "special_requests": extract_special_requests(cleaned),
        "recommended_follow_up": "Review manually",
    }

    lead["summary"] = build_summary(lead)
    lead["appointment_readiness"] = determine_appointment_readiness(lead)

    if lead["appointment_readiness"] == "Ready":
        lead["lead_quality"] = "High"
        lead["recommended_follow_up"] = "Call ASAP"
    elif lead["appointment_readiness"] == "Needs Follow-up":
        lead["lead_quality"] = "Medium"
        lead["recommended_follow_up"] = "Follow up with call"
    else:
        lead["lead_quality"] = "Unknown"
        lead["recommended_follow_up"] = "Review manually"

    return lead
