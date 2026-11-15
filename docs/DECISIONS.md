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

## D9 Reminder idempotency and staleness
Claim-then-send: INSERT notification ON CONFLICT DO NOTHING (UNIQUE appointment_id+kind) before sending; failure deletes the claim so it is
retried; crash between claim and send = at-most-once (accepted; duplicates are worse than a missed reminder). Windows: 24h reminder when
start in [now+24h-60m, now+24h], 2h reminder tolerance 30m, so a booking made 3h ahead never gets a bogus '24h' reminder. Selection reads
current state under FOR UPDATE SKIP LOCKED; reschedule deletes notification rows.
## D10 Deep link
Telegram start payload limit is 64 chars of [A-Za-z0-9_-], so a JWT does not fit: token = b64(patient_id|clinic_id|exp) + b64(HMAC-12 bytes).

## D11 Frontend choices
Next.js 16 App Router, all data via TanStack Query on the client (tokens in localStorage: short access token + rotating refresh). Cache Components disabled
(scaffold default) since the app is a client-rendered SPA behind auth; `output: standalone` for a small Docker image; system fonts (no Google Fonts at build time).
Types generated from backend OpenAPI (`backend/scripts/dump_openapi.py` -> `frontend/openapi.json` -> `lib/schema.d.ts`). Trade-off: localStorage tokens are XSS-exposed.
