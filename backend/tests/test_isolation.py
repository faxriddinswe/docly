"""Clinic A must not read or modify clinic B data through ANY tenant endpoint.

Add every new tenant endpoint to ENDPOINTS; the parametrized test then proves isolation for it.
"""

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from tests.helpers import PASSWORD, signup
from tests.test_scheduling import make_doctor


async def _make_b_resources(client: AsyncClient, b: dict[str, Any]) -> dict[str, str]:
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
    ids = await make_doctor(client, b)
    off = await client.post(
        f"/doctors/{ids['doctor']['id']}/time-off",
        headers=b["h"],
        json={"starts_at": "2030-03-04T09:00:00+05:00", "ends_at": "2030-03-04T10:00:00+05:00"},
    )
    return {
        "membership_id": str(r.json()["membership_id"]),
        "doctor_id": ids["doctor"]["id"],
        "service_id": ids["service"]["id"],
        "time_off_id": off.json()["id"],
    }


_TIME_OFF = {"starts_at": "2030-03-05T09:00:00+05:00", "ends_at": "2030-03-05T10:00:00+05:00"}
# (method, path template, json body). EVERY tenant endpoint that takes an id belongs here.
ENDPOINTS: list[tuple[str, str, Any]] = [
    ("DELETE", "/staff/{membership_id}", None),
    ("GET", "/doctors/{doctor_id}", None),
    ("PATCH", "/doctors/{doctor_id}", {"full_name": "Hacked Name"}),
    ("DELETE", "/doctors/{doctor_id}", None),
    ("PUT", "/doctors/{doctor_id}/services", {"service_ids": []}),
    ("GET", "/doctors/{doctor_id}/working-hours", None),
    ("PUT", "/doctors/{doctor_id}/working-hours", {"intervals": []}),
    ("GET", "/doctors/{doctor_id}/time-off", None),
    ("POST", "/doctors/{doctor_id}/time-off", _TIME_OFF),
    ("GET", "/services/{service_id}", None),
    ("PATCH", "/services/{service_id}", {"name": "Hacked Name"}),
    ("DELETE", "/services/{service_id}", None),
    ("DELETE", "/time-off/{time_off_id}", None),
]


@pytest.mark.parametrize(("method", "path", "body"), ENDPOINTS)
async def test_clinic_a_cannot_touch_clinic_b(
    client: AsyncClient, method: str, path: str, body: Any
) -> None:
    a, b = await signup(client, "a"), await signup(client, "b")
    ids = await _make_b_resources(client, b)
    r = await client.request(method, path.format(**ids), json=body, headers=a["h"])
    assert r.status_code == 404, r.text
    # B's data is untouched
    d = (await client.get(f"/doctors/{ids['doctor_id']}", headers=b["h"])).json()
    assert d["is_active"] is True and d["full_name"] == "Dr. Karimov"
    s = (await client.get(f"/services/{ids['service_id']}", headers=b["h"])).json()
    assert s["is_active"] is True and s["name"] == "Cleaning"
    assert (
        len((await client.get(f"/doctors/{ids['doctor_id']}/time-off", headers=b["h"])).json()) == 1
    )
    assert (
        len((await client.get(f"/doctors/{ids['doctor_id']}/working-hours", headers=b["h"])).json())
        == 10
    )


async def test_a_cannot_link_b_service_to_own_doctor(client: AsyncClient) -> None:
    a, b = await signup(client, "a"), await signup(client, "b")
    ids = await _make_b_resources(client, b)
    mine = (await client.post("/doctors", headers=a["h"], json={"full_name": "Dr. Mine"})).json()
    r = await client.put(
        f"/doctors/{mine['id']}/services", headers=a["h"], json={"service_ids": [ids["service_id"]]}
    )
    assert r.status_code == 404


async def test_listings_only_show_own_rows(client: AsyncClient) -> None:
    a, b = await signup(client, "a"), await signup(client, "b")
    await _make_b_resources(client, b)
    a_staff = (await client.get("/staff", headers=a["h"])).json()
    assert a_staff["total"] == 1
    assert (await client.get("/doctors", headers=a["h"])).json()["total"] == 0
    assert (await client.get("/services", headers=a["h"])).json()["total"] == 0
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
