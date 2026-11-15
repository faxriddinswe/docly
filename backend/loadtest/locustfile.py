"""Load test: uv run locust -f loadtest/locustfile.py --headless -u 50 -r 10 -t 60s --host http://localhost:8000

Needs the dev stack with the seeded clinic and rate limits raised (see README, 'Load test').
Uses the dev-only /public/dev/otp endpoint to read the fake OTP code.
"""

import random
import uuid
from datetime import date, timedelta

from locust import HttpUser, between, task

SLUG = "smile-dental"


class Patient(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self) -> None:
        info = self.client.get(f"/public/{SLUG}", name="GET /public/{slug}").json()
        self.doctor = info["doctors"][0]["id"]
        self.service = info["services"][0]["id"]

    def _slots(self, name: str) -> list[str]:
        day = date.today() + timedelta(days=random.randint(1, 14))
        r = self.client.get(
            f"/public/{SLUG}/availability",
            params={"doctor_id": self.doctor, "service_id": self.service, "date": day.isoformat()},
            name=name,
        )
        return list(r.json()["slots"]) if r.ok else []

    @task(8)
    def availability(self) -> None:
        self._slots("GET /public/{slug}/availability")

    @task(2)
    def clinic_info(self) -> None:
        self.client.get(f"/public/{SLUG}", name="GET /public/{slug}")

    @task(1)
    def book(self) -> None:
        slots = self._slots("GET /public/{slug}/availability")
        if not slots:
            return
        phone = f"+99890{random.randint(0, 9_999_999):07d}"
        if self.client.post(f"/public/{SLUG}/otp", json={"phone": phone}, name="POST otp").status_code != 204:
            return
        code = self.client.get(f"/public/dev/otp/{phone}", name="GET dev-otp").json()["code"]
        body = {"doctor_id": self.doctor, "service_id": self.service, "starts_at": random.choice(slots),
                "phone": phone, "full_name": f"Load {uuid.uuid4().hex[:6]}", "otp_code": code}
        # 201 = booked, 409 = lost the race / slot taken: both are correct outcomes under load
        with self.client.post(f"/public/{SLUG}/bookings", json=body, name="POST booking", catch_response=True) as r:
            if r.status_code in (201, 409):
                r.success()
            else:
                r.failure(f"unexpected {r.status_code}: {r.text[:100]}")
