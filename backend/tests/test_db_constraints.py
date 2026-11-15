import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine


async def _seed(conn, name: str) -> dict[str, uuid.UUID]:  # type: ignore[no-untyped-def]
    ids = {k: uuid.uuid4() for k in ("clinic", "doctor", "service", "patient")}
    await conn.execute(text("SELECT set_config('app.system','on',true)"))
    await conn.execute(
        text("INSERT INTO clinics(id,name,slug) VALUES (:c,:n,:s)"),
        {"c": ids["clinic"], "n": name, "s": f"{name}-{ids['clinic'].hex[:6]}"},
    )
    await conn.execute(
        text("INSERT INTO doctors(id,clinic_id,full_name) VALUES (:d,:c,'Dr X')"),
        {"d": ids["doctor"], "c": ids["clinic"]},
    )
    await conn.execute(
        text("INSERT INTO services(id,clinic_id,name,duration_minutes,price_minor) VALUES (:s,:c,'Check',30,0)"),
        {"s": ids["service"], "c": ids["clinic"]},
    )
    await conn.execute(
        text("INSERT INTO patients(id,clinic_id,phone,full_name) VALUES (:p,:c,'+998900000000','P')"),
        {"p": ids["patient"], "c": ids["clinic"]},
    )
    return ids


def T(h: int, m: int) -> datetime:
    return datetime(2030, 1, 1, h, m, tzinfo=UTC)


INSERT_APPT = text(
    "INSERT INTO appointments(clinic_id,doctor_id,service_id,patient_id,during,status) "
    "VALUES (:c,:d,:s,:p,tstzrange(CAST(:a AS timestamptz),CAST(:b AS timestamptz)),CAST(:st AS appointment_status))"
)


async def test_exclusion_constraint_blocks_overlap(owner_engine: AsyncEngine) -> None:
    async with owner_engine.begin() as conn:
        ids = await _seed(conn, "excl")
    p = {"c": ids["clinic"], "d": ids["doctor"], "s": ids["service"], "p": ids["patient"]}
    async with owner_engine.begin() as conn:
        await conn.execute(
            INSERT_APPT,
            {**p, "a": T(10, 0), "b": T(10, 30), "st": "booked"},
        )
    with pytest.raises(IntegrityError) as ei:
        async with owner_engine.begin() as conn:
            await conn.execute(
                INSERT_APPT,
                {**p, "a": T(10, 15), "b": T(10, 45), "st": "confirmed"},
            )
    assert "appointments_no_overlap" in str(ei.value)
    async with owner_engine.begin() as conn:  # adjacent slot OK
        await conn.execute(
            INSERT_APPT,
            {**p, "a": T(10, 30), "b": T(11, 0), "st": "booked"},
        )
        # cancelled rows do not block
        await conn.execute(
            INSERT_APPT,
            {**p, "a": T(10, 0), "b": T(10, 30), "st": "cancelled"},
        )


async def test_rls_isolates_tenants(owner_engine: AsyncEngine, app_engine: AsyncEngine) -> None:
    async with owner_engine.begin() as conn:
        a = await _seed(conn, "rlsa")
        b = await _seed(conn, "rlsb")
    async with app_engine.begin() as conn:
        # no tenant context -> nothing visible
        assert (await conn.execute(text("SELECT count(*) FROM doctors"))).scalar_one() == 0
    async with app_engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.current_clinic_id', :c, true)"), {"c": str(a["clinic"])})
        rows = (await conn.execute(text("SELECT id FROM doctors"))).scalars().all()
        assert rows == [a["doctor"]]
        # cannot touch B's rows
        upd = await conn.execute(text("UPDATE doctors SET full_name='hacked' WHERE id=:i"), {"i": b["doctor"]})
        assert upd.rowcount == 0
        # cannot insert into B
        with pytest.raises((DBAPIError, IntegrityError)):
            await conn.execute(
                text("INSERT INTO doctors(clinic_id,full_name) VALUES (:c,'evil')"),
                {"c": b["clinic"]},
            )
