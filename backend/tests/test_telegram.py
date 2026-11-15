import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import text

from app.core.security import make_link_token, parse_link_token
from app.db import system_session
from app.services import reminders, telegram_flow
from app.services.telegram import FakeTransport
from tests.test_booking import book, setup_clinic, slots


async def link_patient(appt_json: dict[str, Any], clinic_id: str, chat_id: int) -> None:
    token = make_link_token(uuid.UUID(appt_json["patient_id"]), uuid.UUID(clinic_id))
    reply = await telegram_flow.handle_start(token, chat_id)
    assert "Rahmat" in reply


async def booked_at(client: AsyncClient, c: dict[str, Any], hours_from_now: float, phone: str) -> dict[str, Any]:
    """Create an appointment starting `hours_from_now` by inserting directly (availability rules need future dates)."""
    from sqlalchemy.dialects.postgresql import Range

    from app.models.tables import Appointment, AppointmentStatus, Patient

    start = (datetime.now(UTC) + timedelta(hours=hours_from_now)).replace(second=0, microsecond=0)
    async with system_session() as s:
        pat = Patient(clinic_id=uuid.UUID(c["o"]["clinic_id"]), phone=phone, full_name="Test Patient")
        s.add(pat)
        await s.flush()
        ap = Appointment(
            clinic_id=uuid.UUID(c["o"]["clinic_id"]),
            doctor_id=uuid.UUID(c["doctor"]["id"]),
            service_id=uuid.UUID(c["service"]["id"]),
            patient_id=pat.id,
            during=Range(start, start + timedelta(minutes=30), bounds="[)"),
            status=AppointmentStatus.booked,
        )
        s.add(ap)
        await s.flush()
        return {"id": str(ap.id), "patient_id": str(pat.id), "start": start}


def test_link_token_roundtrip_and_forgery() -> None:
    p, c = uuid.uuid4(), uuid.uuid4()
    t = make_link_token(p, c)
    assert len(t) == 64 and all(ch.isalnum() or ch in "-_" for ch in t)  # valid Telegram start payload
    assert parse_link_token(t) == (p, c)
    forged = t[:-2] + ("AA" if not t.endswith("AA") else "BB")
    assert parse_link_token(forged) is None
    assert parse_link_token(make_link_token(p, c, ttl_hours=-1)) is None  # expired
    assert parse_link_token("short") is None


async def test_deep_link_booking_response_and_linking(client: AsyncClient, monkeypatch: Any) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "docly_test_bot")
    get_settings.cache_clear()
    c = await setup_clinic(client)
    r = await book(client, c, (await slots(client, c))[0])
    link = r.json()["telegram_link"]
    assert link.startswith("https://t.me/docly_test_bot?start=")
    token = link.split("start=")[1]
    assert await telegram_flow.handle_start(token, 555001)
    async with system_session() as s:
        chat = (
            await s.execute(
                text("SELECT telegram_chat_id FROM patients WHERE id=:i"), {"i": r.json()["appointment"]["patient_id"]}
            )
        ).scalar_one()
    assert chat == 555001
    assert "yaroqsiz" in await telegram_flow.handle_start("x" * 64, 1)
    monkeypatch.delenv("TELEGRAM_BOT_USERNAME")
    get_settings.cache_clear()


async def test_reminders_24h_and_2h_are_idempotent(client: AsyncClient) -> None:
    c = await setup_clinic(client)
    a = await booked_at(client, c, 24.0, "+998901000001")
    await link_patient(a, c["o"]["clinic_id"], 777001)
    t = FakeTransport()
    now = datetime.now(UTC)
    assert await reminders.run_reminder_scan(t, now) == 1
    assert await reminders.run_reminder_scan(t, now) == 0  # idempotent: second scan sends nothing
    assert await reminders.run_reminder_scan(t, now + timedelta(minutes=1)) == 0
    assert len(t.sent) == 1 and t.sent[0].chat_id == 777001 and "ertaga" in t.sent[0].text
    assert [b.callback_data for b in t.sent[0].buttons or []] == [f"c:{a['id']}", f"x:{a['id']}"]
    # 22h later the 2h reminder fires exactly once
    later = a["start"] - timedelta(hours=2)
    assert await reminders.run_reminder_scan(t, later) == 1
    assert await reminders.run_reminder_scan(t, later) == 0
    assert "bugun" in t.sent[1].text
    async with system_session() as s:
        kinds = (
            (
                await s.execute(
                    text("SELECT kind FROM notifications WHERE appointment_id=:i ORDER BY kind"), {"i": a["id"]}
                )
            )
            .scalars()
            .all()
        )
    assert kinds == ["reminder_24h", "reminder_2h"]


async def test_parallel_scans_send_once(client: AsyncClient) -> None:
    import asyncio

    c = await setup_clinic(client)
    a = await booked_at(client, c, 24.0, "+998901000002")
    await link_patient(a, c["o"]["clinic_id"], 777002)
    t = FakeTransport()
    now = datetime.now(UTC)
    results = await asyncio.gather(*[reminders.run_reminder_scan(t, now) for _ in range(6)])
    assert sum(results) == 1 and len(t.sent) == 1


async def test_no_reminders_for_cancelled_unlinked_or_out_of_window(client: AsyncClient) -> None:
    c = await setup_clinic(client)
    cancelled = await booked_at(client, c, 24.0, "+998901000003")
    unlinked = await booked_at(client, c, 23.5, "+998901000004")
    far = await booked_at(client, c, 30.0, "+998901000005")
    for x, chat in ((cancelled, 1), (far, 3)):
        await link_patient(x, c["o"]["clinic_id"], chat)
    r = await client.patch(f"/appointments/{cancelled['id']}/status", headers=c["o"]["h"], json={"status": "cancelled"})
    assert r.status_code == 200
    t = FakeTransport()
    assert await reminders.run_reminder_scan(t, datetime.now(UTC)) == 0
    assert t.sent == [] and unlinked


async def test_reschedule_clears_stale_reminders_and_new_time_gets_new_ones(client: AsyncClient) -> None:
    c = await setup_clinic(client)
    sl = await slots(client, c)
    r = await book(client, c, sl[0], "+998901000006")
    appt_id, patient_id = r.json()["appointment"]["id"], r.json()["appointment"]["patient_id"]
    await link_patient({"patient_id": patient_id}, c["o"]["clinic_id"], 777006)
    start = datetime.fromisoformat(r.json()["appointment"]["starts_at"])
    t = FakeTransport()
    # reminder for the original time
    assert await reminders.run_reminder_scan(t, start - timedelta(hours=24)) == 1
    # patient moves the appointment: stale notification rows are cleared
    token = r.json()["manage_token"]
    moved = await client.post(f"/public/manage/{token}/reschedule", json={"starts_at": sl[6]})
    assert moved.status_code == 200
    async with system_session() as s:
        n = (
            await s.execute(text("SELECT count(*) FROM notifications WHERE appointment_id=:i"), {"i": appt_id})
        ).scalar_one()
    assert n == 0
    # the OLD time no longer triggers anything...
    assert await reminders.run_reminder_scan(t, start - timedelta(hours=24)) == 0
    # ...and the NEW time triggers exactly one reminder
    new_start = datetime.fromisoformat(moved.json()["starts_at"])
    assert await reminders.run_reminder_scan(t, new_start - timedelta(hours=24)) == 1
    assert len(t.sent) == 2


async def test_send_failure_is_retried_not_lost(client: AsyncClient) -> None:
    c = await setup_clinic(client)
    a = await booked_at(client, c, 24.0, "+998901000007")
    await link_patient(a, c["o"]["clinic_id"], 777007)
    t = FakeTransport(fail_next=True)
    now = datetime.now(UTC)
    assert await reminders.run_reminder_scan(t, now) == 0  # outage
    assert await reminders.run_reminder_scan(t, now) == 1  # retried on next scan
    assert await reminders.run_reminder_scan(t, now) == 0


async def test_inline_confirm_and_cancel_authorization(client: AsyncClient) -> None:
    c = await setup_clinic(client)
    a = await booked_at(client, c, 5.0, "+998901000008")
    await link_patient(a, c["o"]["clinic_id"], 777008)
    assert "tegishli emas" in await telegram_flow.handle_callback(f"c:{a['id']}", 999)  # stranger
    assert "tasdiqlandi" in await telegram_flow.handle_callback(f"c:{a['id']}", 777008)
    assert (await client.get(f"/appointments/{a['id']}", headers=c["o"]["h"])).json()["status"] == "confirmed"
    assert "bekor qilindi" in await telegram_flow.handle_callback(f"x:{a['id']}", 777008)
    assert (await client.get(f"/appointments/{a['id']}", headers=c["o"]["h"])).json()["status"] == "cancelled"
    assert "o'zgartirib bo'lmaydi" in await telegram_flow.handle_callback(f"c:{a['id']}", 777008)
    assert "Noto'g'ri" in await telegram_flow.handle_callback("zzz", 777008)


async def test_arq_worker_runs_the_scan(client: AsyncClient) -> None:
    """Wiring test: enqueue the real ARQ function and run a real worker over real Redis."""
    from arq import create_pool
    from arq.worker import Worker

    from app.worker import WorkerSettings

    c = await setup_clinic(client)
    a = await booked_at(client, c, 24.0, "+998901000009")
    await link_patient(a, c["o"]["clinic_id"], 777009)
    fake = FakeTransport()

    async def startup(ctx: dict[str, Any]) -> None:
        ctx["transport"] = fake

    pool = await create_pool(WorkerSettings.redis_settings)
    job = await pool.enqueue_job("scan_reminders")
    assert job is not None
    worker = Worker(
        functions=WorkerSettings.functions,
        redis_settings=WorkerSettings.redis_settings,
        on_startup=startup,
        burst=True,
        poll_delay=0.1,
    )
    await worker.main()
    assert await job.result() == 1 and len(fake.sent) == 1
    await worker.close()
    await pool.aclose()
