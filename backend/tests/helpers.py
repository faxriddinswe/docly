import uuid
from typing import Any

from httpx import AsyncClient

PASSWORD = "correct-horse-battery"


async def signup(client: AsyncClient, prefix: str = "c") -> dict[str, Any]:
    tag = uuid.uuid4().hex[:8]
    body = {
        "clinic_name": f"Clinic {tag}",
        "slug": f"{prefix}-{tag}",
        "full_name": "Owner Name",
        "email": f"{prefix}-{tag}@example.com",
        "password": PASSWORD,
    }
    r = await client.post("/auth/signup", json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    return {
        **data,
        "email": body["email"],
        "slug": body["slug"],
        "h": {"Authorization": f"Bearer {data['access_token']}"},
    }
