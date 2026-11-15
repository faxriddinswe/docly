"""Clinic A must not read or modify clinic B data through ANY tenant endpoint.

Add every new tenant endpoint to ENDPOINTS; the parametrized test then proves isolation for it.
"""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from tests.helpers import PASSWORD, signup


async def _make_b_staff(client: AsyncClient, b: dict[str, Any]) -> str:
    r = await client.post(
        "/staff",
        json={
            "email": f"{uuid.uuid4().hex[:8]}@example.com",
            "full_name": "B Doctor",
            "password": PASSWORD,
            "role": "doctor",
        },
        headers=b["h"],
    )
    return str(r.json()["membership_id"])


# (method, path template using {membership_id}, json body or None)
ENDPOINTS = [
    ("DELETE", "/staff/{membership_id}", None),
]


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
async def test_clinic_a_cannot_touch_clinic_b(
    client: AsyncClient, method: str, path: str, body: Any
) -> None:
    a, b = await signup(client, "a"), await signup(client, "b")
    mid = await _make_b_staff(client, b)
    r = await client.request(method, path.format(membership_id=mid), json=body, headers=a["h"])
    assert r.status_code == 404, r.text
    # and B's data is still intact
    staff = (await client.get("/staff", headers=b["h"])).json()
    assert mid in [s["membership_id"] for s in staff["items"]]


async def test_listings_only_show_own_rows(client: AsyncClient) -> None:
    a, b = await signup(client, "a"), await signup(client, "b")
    await _make_b_staff(client, b)
    a_staff = (await client.get("/staff", headers=a["h"])).json()
    assert a_staff["total"] == 1
    assert (await client.get("/clinic", headers=a["h"])).json()["id"] == a["clinic_id"]


async def test_forged_clinic_id_in_body_is_ignored(client: AsyncClient) -> None:
    a, b = await signup(client, "a"), await signup(client, "b")
    r = await client.post(
        "/staff",
        json={
            "email": f"{uuid.uuid4().hex[:8]}@example.com",
            "full_name": "Sneaky Person",
            "password": PASSWORD,
            "role": "doctor",
            "clinic_id": b["clinic_id"],
        },
        headers=a["h"],
    )
    assert r.status_code == 201
    assert r.json()["membership_id"] not in [
        s["membership_id"] for s in (await client.get("/staff", headers=b["h"])).json()["items"]
    ]
