import httpx


async def send_lead_to_n8n(webhook_url: str, payload: dict) -> bool:
    if not webhook_url:
        print("[ellie] No n8n webhook configured. Skipping send.")
        return False

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(webhook_url, json=payload)
        response.raise_for_status()
        return True
