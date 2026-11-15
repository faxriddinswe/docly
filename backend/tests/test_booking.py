import asyncio
from collections import Counter
from typing import Any

from httpx import AsyncClient

from app.core.redis import get_redis
from tests.helpers import signup
from tests.test_scheduling import MONDAY, make_doctor


async def setup_clinic(client: AsyncClient) -> dict[str, Any]:
    o = await signup(client)
    ids = await make_doctor(client, o)
    return {"o": o, **ids}


async def slots(client: AsyncClient, c: dict[str, Any], day: str = MONDAY) -> list[str]:
    r = await client.get(
        f"/public/{c['o']['slug']}/availability",
        params={"doctor_id": c["doctor"]["id"], "service_id": c["service"]["id"], "date": day},
    )
    return list(r.json()["slots"])


async def otp_for(client: AsyncClient, c: dict[str, Any], phone: str) -> str:
    r = await client.post(f"/public/{c['o']['slug']}/otp", json={"phone": phone})
    assert r.status_code == 204, r.text
    code = await get_redis().get(f"otp:outbox:{phone}")
    assert code
    return str(code)


def payload(c: dict[str, Any], start: str, phone: str, code: str, name: str = "Ali Valiyev") -> dict[str, Any]:
    return {
        "doctor_id": c["doctor"]["id"],
        "service_id": c["service"]["id"],
        "starts_at": start,
        "phone": phone,
        "full_name": name,
        "otp_code": code,
    }


async def book(client: AsyncClient, c: dict[str, Any], start: str, phone: str = "+998901112233") -> Any:
    code = await otp_for(client, c, phone)
    return await client.post(f"/public/{c['o']['slug']}/bookings", json=payload(c, start, phone, code))


async def test_full_public_flow(client: AsyncClient) -> None:
    c = await setup_clinic(client)
    first = (await slots(client, c))[0]
    r = await book(client, c, first)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["appointment"]["status"] == "booked" and body["manage_token"]
    assert first not in await slots(client, c)  # slot disappears
    # staff sees it, patient created
    appts = (await client.get("/appointments", headers=c["o"]["h"])).json()
    assert appts["total"] == 1 and appts["items"][0]["patient_phone"] == "+998901112233"
    pts = (await client.get("/patients", headers=c["o"]["h"])).json()
    assert pts["total"] == 1
    hist = (await client.get(f"/patients/{pts['items'][0]['id']}/appointments", headers=c["o"]["h"])).json()
    assert len(hist) == 1


async def test_second_booking_same_slot_is_409(client: AsyncClient) -> None:
    c = await setup_clinic(client)
    first = (await slots(client, c))[0]
    assert (await book(client, c, first, "+998901111111")).status_code == 201
    r = await book(client, c, first, "+998902222222")
    assert r.status_code == 409  # pre-check catches it; the DB constraint is proven in the concurrency test


async def test_concurrent_bookings_exactly_one_wins(client: AsyncClient) -> None:
    """N parallel requests for ONE slot: the DB exclusion constraint must let exactly one through."""
    c = await setup_clinic(client)
    start = (await slots(client, c))[3]
    n = 12
    phones = [f"+99890{i:07d}" for i in range(1, n + 1)]
    codes = [await otp_for(client, c, ph) for ph in phones]
    results = await asyncio.gather(
        *[
            client.post(f"/public/{c['o']['slug']}/bookings", json=payload(c, start, ph, cd, f"Patient {i}"))
            for i, (ph, cd) in enumerate(zip(phones, codes, strict=True))
        ]
    )
    counts = Counter(r.status_code for r in results)
    assert counts[201] == 1, counts
    assert counts[409] == n - 1, counts
    codes_seen = {r.json()["error"]["code"] for r in results if r.status_code == 409}
    assert codes_seen <= {"SLOT_TAKEN", "SLOT_UNAVAILABLE"}
    assert (await client.get("/appointments", headers=c["o"]["h"])).json()["total"] == 1


async def test_race_decided_by_db_exclusion_constraint(client: AsyncClient, monkeypatch: Any) -> None:
    """Force a TRUE race: a barrier inside the real availability check makes all N requests pass the
    service-layer check simultaneously, so only the PostgreSQL exclusion constraint can stop them."""
    from app.services import scheduling

    n = 10
    barrier = asyncio.Barrier(n)
    real = scheduling.available_slots

    async def synced(*a: Any, **kw: Any) -> Any:
        result = await real(*a, **kw)
        await barrier.wait()
        return result

    c = await setup_clinic(client)
    start = (await slots(client, c))[4]  # look the slot up BEFORE patching (the endpoint uses it too)
    monkeypatch.setattr(scheduling, "available_slots", synced)
    phones = [f"+99891{i:07d}" for i in range(1, n + 1)]
    codes = [await otp_for(client, c, ph) for ph in phones]
    results = await asyncio.gather(
        *[
            client.post(f"/public/{c['o']['slug']}/bookings", json=payload(c, start, ph, cd, f"Racer {i}"))
            for i, (ph, cd) in enumerate(zip(phones, codes, strict=True))
        ]
    )
    counts = Counter(r.status_code for r in results)
    assert counts[201] == 1 and counts[409] == n - 1, counts
    assert {r.json()["error"]["code"] for r in results if r.status_code == 409} == {"SLOT_TAKEN"}


async def test_otp_rules(client: AsyncClient) -> None:
    c = await setup_clinic(client)
    start = (await slots(client, c))[0]
    phone = "+998903334455"
    code = await otp_for(client, c, phone)
    bad = await client.post(
        f"/public/{c['o']['slug']}/bookings",
        json=payload(c, start, phone, "000000" if code != "000000" else "111111"),
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "OTP_INVALID"
    ok = await client.post(f"/public/{c['o']['slug']}/bookings", json=payload(c, start, phone, code))
    assert ok.status_code == 201
    # code is single use
    again = await client.post(
        f"/public/{c['o']['slug']}/bookings",
        json=payload(c, (await slots(client, c))[0], phone, code),
    )
    assert again.status_code == 422
    # rate limit: 3 OTP requests per phone per window
    p2 = "+998905556677"
    for _ in range(3):
        assert (await client.post(f"/public/{c['o']['slug']}/otp", json={"phone": p2})).status_code == 204
    r = await client.post(f"/public/{c['o']['slug']}/otp", json={"phone": p2})
    assert r.status_code == 429 and r.json()["error"]["code"] == "RATE_LIMITED"
    assert (await client.post(f"/public/{c['o']['slug']}/otp", json={"phone": "123"})).status_code == 422


async def test_otp_brute_force_lockout(client: AsyncClient) -> None:
    c = await setup_clinic(client)
    start = (await slots(client, c))[0]
    phone = "+998907778899"
    real = await otp_for(client, c, phone)
    wrong = "000000" if real != "000000" else "111111"
    statuses = []
    for _ in range(7):
        r = await client.post(f"/public/{c['o']['slug']}/bookings", json=payload(c, start, phone, wrong))
        statuses.append(r.status_code)
    assert statuses[:5] == [422] * 5 and statuses[5:] == [429, 429]
    # even the correct code no longer works after lockout
    r = await client.post(f"/public/{c['o']['slug']}/bookings", json=payload(c, start, phone, real))
    assert r.status_code in (422, 429)


async def test_service_layer_rules(client: AsyncClient) -> None:
    c = await setup_clinic(client)
    sl = await slots(client, c)
    # off-grid time, lunch time, weekend, and past are all rejected
    for i, bad in enumerate(
        (
            "2030-03-04T04:10:00+00:00",
            "2030-03-04T08:00:00+00:00",
            "2030-03-09T05:00:00+00:00",
            "2020-03-04T04:00:00+00:00",
        )
    ):
        r = await book(client, c, bad, f"+99890000000{i}")
        assert r.status_code == 409 and r.json()["error"]["code"] == "SLOT_UNAVAILABLE", (
            bad,
            r.text,
        )
    assert sl  # sanity


async def test_cancel_and_reschedule_via_manage_token(client: AsyncClient) -> None:
    c = await setup_clinic(client)
    sl = await slots(client, c)
    r = await book(client, c, sl[0])
    token = r.json()["manage_token"]
    moved = await client.post(f"/public/manage/{token}/reschedule", json={"starts_at": sl[5]})
    assert moved.status_code == 200 and moved.json()["starts_at"].startswith(sl[5][:16])
    after = await slots(client, c)
    assert sl[0] in after and sl[5] not in after  # old slot freed
    cancelled = await client.post(f"/public/manage/{token}/cancel")
    assert cancelled.json()["status"] == "cancelled"
    assert sl[5] in await slots(client, c)
    # cancelled appointment cannot be rescheduled or cancelled again
    assert (await client.post(f"/public/manage/{token}/reschedule", json={"starts_at": sl[1]})).status_code == 409
    assert (await client.post(f"/public/manage/{token}/cancel")).status_code == 409
    assert (await client.get("/public/manage/garbage")).status_code == 401


async def test_staff_status_transitions_and_audit(client: AsyncClient) -> None:
    c = await setup_clinic(client)
    h = c["o"]["h"]
    sl = await slots(client, c)
    r = await client.post(
        "/appointments",
        headers=h,
        json={
            "doctor_id": c["doctor"]["id"],
            "service_id": c["service"]["id"],
            "starts_at": sl[2],
            "phone": "+998909998877",
            "full_name": "Walk In",
        },
    )
    assert r.status_code == 201
    aid = r.json()["id"]
    assert (
        await client.patch(f"/appointments/{aid}/status", headers=h, json={"status": "confirmed"})
    ).status_code == 200
    assert (
        await client.patch(f"/appointments/{aid}/status", headers=h, json={"status": "completed"})
    ).status_code == 200
    bad = await client.patch(f"/appointments/{aid}/status", headers=h, json={"status": "booked"})
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "INVALID_TRANSITION"
    # audit rows exist (read as owner of DB through system session)
    from sqlalchemy import text

    from app.db import system_session

    async with system_session() as s:
        acts = (
            (
                await s.execute(
                    text("SELECT action FROM audit_log WHERE entity_id=:i ORDER BY created_at"),
                    {"i": aid},
                )
            )
            .scalars()
            .all()
        )
    assert acts == ["appointment.create", "appointment.status", "appointment.status"]


async def test_clinic_b_cannot_see_or_change_a_appointments(client: AsyncClient) -> None:
    a = await setup_clinic(client)
    b = await signup(client, "b")
    r = await book(client, a, (await slots(client, a))[0])
    aid = r.json()["appointment"]["id"]
    pid = r.json()["appointment"]["patient_id"]
    for method, path, body in [
        ("GET", f"/appointments/{aid}", None),
        ("PATCH", f"/appointments/{aid}/status", {"status": "cancelled"}),
        ("POST", f"/appointments/{aid}/reschedule", {"starts_at": "2030-03-04T05:00:00+00:00"}),
        ("GET", f"/patients/{pid}/appointments", None),
    ]:
        resp = await client.request(method, path, json=body, headers=b["h"])
        assert resp.status_code == 404, (path, resp.text)
    assert (await client.get("/appointments", headers=b["h"])).json()["total"] == 0
    assert (await client.get("/patients", headers=b["h"])).json()["total"] == 0
    assert (await client.get(f"/appointments/{aid}", headers=a["o"]["h"])).json()["status"] == "booked"


async def test_dev_otp_endpoint_exists_only_outside_prod(client: AsyncClient) -> None:
    c = await setup_clinic(client)
    code = await otp_for(client, c, "+998901234500")
    r = await client.get("/public/dev/otp/+998901234500")
    assert r.status_code == 200 and r.json()["code"] == code
    import subprocess
    import sys

    out = subprocess.run(  # noqa: ASYNC221 - one-off child process to check prod route set
        [
            sys.executable,
            "-c",
            "from app.main import create_app; print(any('/dev/otp' in p for p in create_app().openapi()['paths']))",
        ],
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "ENV": "prod", "JWT_SECRET": "x" * 40},
    )
    assert out.stdout.strip().endswith("False"), out.stderr
