"""Seed two synthetic clinics (fake data only). Idempotent: skips if slugs exist.

Run: uv run python -m app.seed
"""

import asyncio
import uuid
from datetime import time

from argon2 import PasswordHasher
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

CLINICS = [
    ("Smile Dental", "smile-dental", "owner@smile.example"),
    ("Chilonzor Medical", "chilonzor-medical", "owner@chilonzor.example"),
]


async def seed() -> None:
    engine = create_async_engine(get_settings().migration_database_url)
    ph = PasswordHasher()
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.system','on',true)"))
        for name, slug, email in CLINICS:
            if (
                await conn.execute(text("SELECT 1 FROM clinics WHERE slug=:s"), {"s": slug})
            ).first():
                continue
            cid, uid, did, sid = (uuid.uuid4() for _ in range(4))
            await conn.execute(
                text("INSERT INTO clinics(id,name,slug) VALUES (:i,:n,:s)"),
                {"i": cid, "n": name, "s": slug},
            )
            await conn.execute(
                text(
                    "INSERT INTO users(id,email,password_hash,full_name) VALUES (:i,:e,:h,'Demo Owner')"
                ),
                {"i": uid, "e": email, "h": ph.hash("demo-password-123")},
            )
            await conn.execute(
                text(
                    "INSERT INTO clinic_memberships(clinic_id,user_id,role) VALUES (:c,:u,'owner')"
                ),
                {"c": cid, "u": uid},
            )
            await conn.execute(
                text(
                    "INSERT INTO doctors(id,clinic_id,full_name,specialty) VALUES (:d,:c,'Dr. Aliyev','Dentist')"
                ),
                {"d": did, "c": cid},
            )
            await conn.execute(
                text(
                    "INSERT INTO services(id,clinic_id,name,duration_minutes,price_minor) "
                    "VALUES (:s,:c,'Consultation',30,15000000)"
                ),
                {"s": sid, "c": cid},
            )
            await conn.execute(
                text(
                    "INSERT INTO doctor_services(doctor_id,service_id,clinic_id) VALUES (:d,:s,:c)"
                ),
                {"d": did, "s": sid, "c": cid},
            )
            for wd in range(5):  # Mon-Fri, lunch break 13-14
                for a, b in ((time(9), time(13)), (time(14), time(18))):
                    await conn.execute(
                        text(
                            "INSERT INTO working_hours(clinic_id,doctor_id,weekday,start_time,end_time) "
                            "VALUES (:c,:d,:w,:a,:b)"
                        ),
                        {"c": cid, "d": did, "w": wd, "a": a, "b": b},
                    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
