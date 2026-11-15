# Decisions
## D1 Project name
Docly (owner message during Phase 0). Caddy snippet will be deploy/docly.caddy.
## D2 Tooling
uv for Python (lockfile, fast, official Astral package from PyPI); Python 3.12 as required by spec though system has 3.14.
Dev DB/Redis host ports 5442/6390 to avoid collisions. mypy strict on app.domain and app.services only, per spec.

## D3 Two-layer tenancy
App layer: ScopedRepo + clinic_id from JWT only. DB layer: RLS FORCE on every tenant table, policy compares clinic_id with
`app.current_clinic_id` (set per transaction via set_config(...,true)). App connects as non-superuser `docly_app`
(superusers bypass RLS); migrations run as owner `docly`. Escape hatch `app.system='on'` is used only by system_session()
(auth lookups, public slug resolution, jobs). Trade-off: any code path that calls system_session() is trusted; it is grep-able.
## D4 Refresh tokens
Opaque random 48 bytes, stored as sha256, single-use rotation within a family; reuse revokes the family. Access JWT HS256, 15 min.
Login for a user in several clinics requires clinic_slug (400 CLINIC_REQUIRED lists options).

## D5 Slot grid
Slots lie on a grid of `service.duration` starting at each working interval's start; a slot must fit inside one interval
(never crosses lunch). Chosen over a fixed 15-min step: clean UI, fewer fragmented gaps. Trade-off: less flexible start times.
## D6 Soft delete for doctors/services
DELETE sets is_active=false; appointments keep RESTRICT foreign keys so history never dangles.

## D7 Booking validation layers
1) service layer: slot must be exactly in computed availability (hours, time off, grid, notice, past, existing bookings);
2) DB exclusion constraint is the source of truth: losing a race raises 23P01, mapped to 409 SLOT_TAKEN inside a savepoint
so the request transaction stays usable. Pre-check failures return 409 SLOT_UNAVAILABLE.
## D8 Patient self-service
No patient accounts: booking returns a signed 'manage' JWT (90 days) allowing view/cancel/reschedule of that one appointment.
OTP is verified at booking time (code stored hashed in Redis, 5 attempts, single use, per-phone/IP rate limits).
