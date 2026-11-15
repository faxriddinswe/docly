from datetime import datetime
from typing import Any

from httpx import AsyncClient

from tests.helpers import signup

MONDAY = "2030-03-04"


async def make_doctor(client: AsyncClient, owner: dict[str, Any], hours: bool = True) -> dict[str, Any]:
    h = owner["h"]
    svc = (
        await client.post(
            "/services",
            headers=h,
            json={"name": "Cleaning", "duration_minutes": 30, "price_minor": 10000000},
        )
    ).json()
    doc = (await client.post("/doctors", headers=h, json={"full_name": "Dr. Karimov"})).json()
    r = await client.put(f"/doctors/{doc['id']}/services", headers=h, json={"service_ids": [svc["id"]]})
    assert r.status_code == 200, r.text
    if hours:
        iv = [
            {"weekday": d, "start_time": s, "end_time": e}
            for d in range(5)
            for s, e in (("09:00:00", "13:00:00"), ("14:00:00", "18:00:00"))
        ]
        r = await client.put(f"/doctors/{doc['id']}/working-hours", headers=h, json={"intervals": iv})
        assert r.status_code == 200, r.text
    return {"doctor": doc, "service": svc}


async def test_crud_and_validation(client: AsyncClient) -> None:
    o = await signup(client)
    ids = await make_doctor(client, o)
    d = (await client.get(f"/doctors/{ids['doctor']['id']}", headers=o["h"])).json()
    assert d["service_ids"] == [ids["service"]["id"]]
    bad = await client.post("/services", headers=o["h"], json={"name": "X1", "duration_minutes": 0, "price_minor": 1})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "VALIDATION_ERROR"
    overlap = await client.put(
        f"/doctors/{d['id']}/working-hours",
        headers=o["h"],
        json={
            "intervals": [
                {"weekday": 0, "start_time": "09:00:00", "end_time": "12:00:00"},
                {"weekday": 0, "start_time": "11:00:00", "end_time": "13:00:00"},
            ]
        },
    )
    assert overlap.status_code == 422 and overlap.json()["error"]["code"] == "OVERLAPPING_HOURS"
    r = await client.patch(f"/services/{ids['service']['id']}", headers=o["h"], json={"price_minor": 5})
    assert r.json()["price_minor"] == 5
    assert (await client.delete(f"/doctors/{d['id']}", headers=o["h"])).status_code == 204
    page = (await client.get("/doctors?limit=1", headers=o["h"])).json()
    assert page["total"] == 1 and page["limit"] == 1 and page["items"][0]["is_active"] is False


async def test_public_availability(client: AsyncClient) -> None:
    o = await signup(client)
    ids = await make_doctor(client, o)
    q = {"doctor_id": ids["doctor"]["id"], "service_id": ids["service"]["id"], "date": MONDAY}
    r = await client.get(f"/public/{o['slug']}/availability", params=q)
    assert r.status_code == 200
    body = r.json()
    assert body["timezone"] == "Asia/Tashkent" and len(body["slots"]) == 16
    assert body["slots"][0].startswith("2030-03-04T04:00:00")  # 09:00 Tashkent = 04:00 UTC
    # time off for the morning removes 09:00-13:00
    off = await client.post(
        f"/doctors/{ids['doctor']['id']}/time-off",
        headers=o["h"],
        json={
            "starts_at": "2030-03-04T09:00:00+05:00",
            "ends_at": "2030-03-04T13:00:00+05:00",
            "reason": "x",
        },
    )
    assert off.status_code == 201
    body = (await client.get(f"/public/{o['slug']}/availability", params=q)).json()
    assert len(body["slots"]) == 8
    assert all(datetime.fromisoformat(s).hour >= 9 for s in body["slots"])  # >= 14:00 local = 09:00 UTC
    # weekend: no hours configured
    q["date"] = "2030-03-09"
    assert (await client.get(f"/public/{o['slug']}/availability", params=q)).json()["slots"] == []


async def test_public_unknown_and_suspended(client: AsyncClient) -> None:
    r = await client.get("/public/no-such-clinic")
    assert r.status_code == 404 and r.json()["error"]["code"] == "CLINIC_NOT_FOUND"


async def test_public_info_lists_services_and_doctors(client: AsyncClient) -> None:
    o = await signup(client)
    await make_doctor(client, o)
    r = (await client.get(f"/public/{o['slug']}")).json()
    assert len(r["services"]) == 1 and len(r["doctors"]) == 1 and r["doctors"][0]["service_ids"]
