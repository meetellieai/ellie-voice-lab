import re


def extract_caller_name(text: str) -> str:
    """Extract caller name from transcript using various name patterns."""
    lower = text.lower()

    # Patterns: "my name is X", "this is X", "I'm X", "I am X", "X speaking", "it's X again"
    patterns = [
        r"my name is\s+([a-zA-Z]+)",
        r"this is\s+([a-zA-Z]+)(?:\s|,|\.)",
        r"i'm\s+([a-zA-Z]+)(?:\s|,|\.)",
        r"i am\s+([a-zA-Z]+)(?:\s|,|\.)",
        r"([a-zA-Z]+)\s+speaking",
        r"(?:it's|it is)\s+([a-zA-Z]+)\s+(?:again|speaking)",
    ]

    for pattern in patterns:
        match = re.search(pattern, lower, re.IGNORECASE)
        if match:
            name = match.group(1).capitalize()
            # Filter out common words that aren't names
            if name.lower() not in ["just", "the", "a", "an", "ok", "yeah", "yes", "no"]:
                return name

    return ""


def extract_appointment_type(text: str) -> str:
    """Extract the type of appointment being scheduled."""
    lower = text.lower()

    appointment_keywords = [
        "estimate",
        "consultation",
        "appointment",
        "service call",
        "callback",
        "inspection",
        "repair visit",
        "intake call",
        "quote",
    ]

    for keyword in appointment_keywords:
        if keyword in lower:
            return keyword

    return ""


def extract_appointment_date(text: str) -> str:
    """Extract the preferred appointment date."""
    lower = text.lower()

    date_patterns = [
        "today",
        "tomorrow",
        "this week",
        "next week",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "next monday",
        "next tuesday",
        "next wednesday",
        "next thursday",
        "next friday",
        "next saturday",
        "next sunday",
    ]

    for pattern in date_patterns:
        if pattern in lower:
            return pattern

    # Try to match dates like "May 15", "5/15", etc.
    date_match = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})", lower, re.IGNORECASE)
    if date_match:
        return f"{date_match.group(1)} {date_match.group(2)}"

    # Try MM/DD format
    date_match = re.search(r"(\d{1,2})/(\d{1,2})", text)
    if date_match:
        return f"{date_match.group(1)}/{date_match.group(2)}"

    return ""


def extract_appointment_time_window(text: str) -> str:
    """Extract the preferred appointment time window."""
    lower = text.lower()

    time_windows = [
        "morning",
        "afternoon",
        "evening",
        "after work",
        "before noon",
        "after 5",
        "around 3",
        "3pm",
        "anytime",
    ]

    for window in time_windows:
        if window in lower:
            return window

    # Try to match time ranges like "between 2 and 4", "2-4pm"
    time_match = re.search(r"between\s+(\d{1,2})\s+and\s+(\d{1,2})", lower)
    if time_match:
        return f"between {time_match.group(1)} and {time_match.group(2)}"

    time_match = re.search(r"(\d{1,2})[\s-]*to[\s-]*(\d{1,2})\s*(am|pm)", lower)
    if time_match:
        return f"{time_match.group(1)} to {time_match.group(2)} {time_match.group(3)}"

    return ""


def extract_issue_description(text: str) -> str:
    """Extract the issue/problem description from transcript."""
    lower = text.lower()

    # Look for descriptive phrases
    issue_keywords = [
        "ants",
        "roaches",
        "leak",
        "broken",
        "damaged",
        "not working",
        "broken down",
        "needs repair",
        "crack",
        "water damage",
        "mold",
        "stain",
        "scratch",
        "dent",
    ]

    found_issues = [word for word in issue_keywords if word in lower]
    if found_issues:
        return found_issues[0]

    # Try to extract a sentence about what they need
    # Look for "because", "due to", "have", "need" patterns
    patterns = [
        r"because\s+([^.!?]+)",
        r"have\s+([^.!?]+)",
        r"need(?:s?)?\s+([^.!?]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            desc = match.group(1).strip()
            if len(desc) < 100:
                return desc

    return ""


def extract_preferred_contact_method(text: str) -> str:
    """Extract the preferred contact method (call, text, email)."""
    lower = text.lower()

    if any(word in lower for word in ["text", "text me", "sms"]):
        return "text"
    elif any(word in lower for word in ["email", "e-mail"]):
        return "email"
    elif any(word in lower for word in ["call", "phone call"]):
        return "call"

    return ""


def extract_special_requests(text: str) -> str:
    """Extract any special requests or accessibility needs."""
    lower = text.lower()

    request_keywords = [
        "wheelchair",
        "accessible",
        "service dog",
        "allergy",
        "medical",
        "fragrance free",
        "after hours",
        "weekend",
        "no pets",
        "kids present",
        "elderly",
    ]

    found = [word for word in request_keywords if word in lower]
    if found:
        return "; ".join(found)

    return ""


def determine_appointment_readiness(lead: dict) -> str:
    """Determine if appointment has all necessary info."""
    has_name = bool(lead.get("caller_name"))
    has_phone = bool(lead.get("phone"))
    has_service = bool(lead.get("service_needed") or lead.get("issue_description"))
    has_time = bool(lead.get("appointment_time_window") or lead.get("preferred_callback_time"))

    if has_name and has_phone and has_service and has_time:
        return "Ready"
    elif has_phone and has_service:
        return "Needs Follow-up"
    else:
        return "Incomplete"


def extract_lead_from_text(text: str) -> dict:
    """
    Extract lead information from call transcript.
    Optimized for appointment scheduling and intake.
    """
    text = text or ""
    lower = text.lower()

    lead = {
        "caller_name": "",
        "phone": "",
        "location": "",
        "service_needed": "",
        "urgency": "",
        "preferred_callback_time": "",
        "notes": "",
        "lead_quality": "Unknown",
        "recommended_follow_up": "Review manually",
        "appointment_type": "",
        "appointment_date": "",
        "appointment_time_window": "",
        "issue_description": "",
        "preferred_contact_method": "",
        "special_requests": "",
        "appointment_readiness": "Incomplete",
    }

    # Extract caller name
    lead["caller_name"] = extract_caller_name(text)

    # Extract phone
    phone_match = re.search(r"(\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})", text)
    if phone_match:
        lead["phone"] = phone_match.group(1)

    # Extract location
    known_locations = [
        "bradenton",
        "sarasota",
        "tampa",
        "st. petersburg",
        "saint petersburg",
        "clearwater",
        "lakewood ranch",
        "palmetto",
        "ellenton"
    ]

    for location in known_locations:
        if location in lower:
            lead["location"] = location.title()
            break

    # Extract service needed
    service_keywords = [
        "roof",
        "roofing",
        "floor",
        "flooring",
        "pest",
        "pest control",
        "ants",
        "roaches",
        "hvac",
        "air conditioning",
        "ac",
        "plumbing",
        "leak",
        "cleaning",
        "landscaping",
        "lawn",
        "estimate",
        "quote",
        "appointment",
        "repair",
        "install",
        "replacement"
    ]

    found_services = [word for word in service_keywords if word in lower]
    if found_services:
        lead["service_needed"] = found_services[0]

    # Extract urgency
    urgency_words = [
        "today",
        "tomorrow",
        "as soon as possible",
        "asap",
        "urgent",
        "emergency",
        "this week",
        "next week"
    ]

    for word in urgency_words:
        if word in lower:
            lead["urgency"] = word
            break

    # Extract preferred callback time
    callback_times = [
        "morning",
        "afternoon",
        "evening",
        "after work",
        "before noon",
        "after 5",
        "anytime"
    ]

    for time_word in callback_times:
        if time_word in lower:
            lead["preferred_callback_time"] = time_word
            break

    # Extract appointment-specific fields
    lead["appointment_type"] = extract_appointment_type(text)
    lead["appointment_date"] = extract_appointment_date(text)
    lead["appointment_time_window"] = extract_appointment_time_window(text)
    lead["issue_description"] = extract_issue_description(text)
    lead["preferred_contact_method"] = extract_preferred_contact_method(text)
    lead["special_requests"] = extract_special_requests(text)

    # Determine appointment readiness
    lead["appointment_readiness"] = determine_appointment_readiness(lead)

    # Set notes to full transcript
    lead["notes"] = text[:500]

    # Update lead quality based on appointment readiness
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
