# Docly — intervyuga tayyorgarlik qo'llanmasi (o'zbekcha)

Har bir bosqich: nima qurildi, nega bunday, qanday ishlaydi, kamchiliklari, va intervyu savollari.

## 0-bosqich. Skelet va muhit
**Nima:** FastAPI ilovasi, `/health` va `/ready`, uv + Python 3.12, ruff, mypy, pytest, docker compose (Postgres + Redis), CI.
**Nega:** `uv` — tez va `uv.lock` bilan versiyalar qotirilgan (supply-chain xavfi kam). `/health` — jarayon tirikmi; `/ready` — baza va Redis ham ishlayaptimi (orkestrator shunga qarab trafik beradi).
**Kamchilik:** mypy faqat `domain/` va `services/` da qat'iy (spetsifikatsiya shunday).
**Savollar**
1. */health va /ready farqi?* — health: jarayon tirik; ready: bog'liqliklar (DB, Redis) tayyor. Ready yiqilsa konteyner o'chmaydi, faqat trafikdan chiqariladi.
2. *Nega testda SQLite emas, haqiqiy PostgreSQL?* — exclusion constraint, RLS, tstzrange faqat Postgres'da bor; SQLite bilan ular test qilinmay qoladi.
3. *Nega versiyalar qotiriladi?* — takrorlanuvchan build va zararli yangi versiyadan himoya.

## 1-bosqich. Ma'lumotlar modeli
**Nima:** jadvallar (clinics, users, memberships, doctors, services, working_hours, time_off, patients, appointments, notifications, audit_log), Alembic migratsiya, `btree_gist`, exclusion constraint, RLS, seed (2 ta soxta klinika).
**Qanday:** `appointments.during` — `tstzrange`. `EXCLUDE USING gist (doctor_id WITH =, during WITH &&) WHERE status IN ('booked','confirmed')` — bir shifokorning faol qabullari kesishmaydi. Pul — butun son (tiyin), float emas.
**Nega:** bu qoida bazada bo'lsa, qaysi kod/klient yozmasin buzib bo'lmaydi.
**Savollar**
1. *Double-booking'ni qanday oldini olasiz?* — Exclusion constraint. Ilova darajasidagi "avval tekshir, keyin yoz" poygada (race) ishlamaydi; constraint atomik.
2. *Nega pul float emas?* — yaxlitlash xatolari; minor unit (tiyin) butun son.
3. *`tstzrange` nima uchun?* — vaqt oralig'i va `&&` (kesishish) operatori, GiST indeks bilan.

## 2-bosqich. Autentifikatsiya va tenantlik
**Nima:** signup (klinika + owner), login, refresh rotatsiyasi, logout, rollar (owner/admin/doctor), superadmin, izolyatsiya testlari.
**Qanday:** parol — argon2. Access JWT 15 daqiqa. Refresh token — tasodifiy, bazada faqat sha256 xeshi; har ishlatilganda yangisi beriladi; eskisi qayta ishlatilsa butun "oila" bekor qilinadi (o'g'irlik belgisi).
**Ikki qatlamli izolyatsiya:** (1) `ScopedRepo` — `clinic_id` JWT'dan, body'dan emas; (2) PostgreSQL RLS — har tranzaksiyada `set_config('app.current_clinic_id', ..., true)`. Ilova superuser emas rol bilan ulanadi (superuser RLS'ni chetlab o'tadi).
**Kamchilik:** `system_session()` ishonchli yo'l — faqat auth, public slug va joblar uchun.
**Savollar**
1. *RLS nima, nega ilova qatlamidan tashqari ham kerak?* — dasturchi `WHERE clinic_id` ni unutsa ham baza boshqa klinika qatorlarini bermaydi: ikkinchi himoya qatlami.
2. *Refresh rotation va reuse detection?* — har refresh bir martalik; eski token qayta kelsa, demak nusxalangan: oila bekor qilinadi.
3. *Nega "noto'g'ri parol" va "foydalanuvchi yo'q" bir xil xato?* — akkaunt mavjudligini aniqlashga (enumeration) yo'l qo'ymaslik.

## 3-bosqich. Jadval yadrosi
**Nima:** shifokor/xizmat/ish vaqti/dam olish CRUD; `domain/availability.py` — sof funksiya (I/O yo'q).
**Algoritm:** bo'sh slotlar = ish vaqti − time_off − faol qabullar. Ish vaqti klinika vaqt zonasidagi "devor soati", natija UTC. Slot ish oralig'iga to'liq sig'ishi shart (tushlikdan o'tmaydi). O'tgan slotlar va minimal ogohlantirish vaqti (min notice) yashiriladi.
**Nega sof funksiya:** bazasiz tez unit-test (tushlik, DST, boshqa zona, min notice).
**Savollar**
1. *Vaqt zonalarini qanday boshqarasiz?* — saqlash UTC; ko'rsatish/hisoblash klinika zonasida (`zoneinfo`).
2. *Nega slot setkasi xizmat davomiyligi bo'yicha?* — soddalik va bo'laklanib ketmaslik; kamchilik — boshlanish vaqtlari kam.
3. *Shifokorni o'chirish nega "soft delete"?* — qabul tarixi uni ko'rsatib turadi (FK RESTRICT).

## 4-bosqich. Bron qilish
**Nima:** public oqim, OTP (Redis, xeshlangan, 5 urinish, bir martalik), `SLOT_TAKEN` 409, bekor qilish/ko'chirish (imzolangan "manage" token), audit log.
**Poyga (race) bo'yicha dars:** 12 ta parallel so'rov — aynan bittasi 201. Ammo xizmat qatlami oldindan tekshiruvi ko'pchilikni ushlab qolgani uchun, constraint ishlashini isbotlash uchun `asyncio.Barrier` bilan haqiqiy poyga testi yozildi. U **deadlock (40P01)** ni topdi: parallel INSERT'lar bir-birini kutib qolishi mumkin. Yechim: shifokor bo'yicha `pg_advisory_xact_lock` + 40P01 ni ham 409 ga xaritalash.
**Savollar**
1. *Parallel bronlarni qanday test qildingiz?* — Barrier orqali hamma so'rov tekshiruvdan bir vaqtda o'tadi; faqat DB constraint hal qiladi → 1×201, qolgani 409.
2. *Advisory lock nima?* — ilova darajasidagi nomlangan qulf; tranzaksiya tugaganda bo'shaydi. Bu yerda faqat deadlock'ni yo'qotadi, to'g'rilikni constraint kafolatlaydi.
3. *OTP'ni nega xeshlab saqlaysiz?* — Redis oqib ketsa ham kodlar ochiq bo'lmasligi uchun; urinishlar cheklangan (6 xonali kodni brute-force qilib bo'lmasin).

## 5-bosqich. Telegram va joblar
**Nima:** `Transport` interfeysi (Fake/Aiogram), imzolangan deep link (64 belgi: 36 bayt payload + 12 bayt HMAC), ARQ cron har daqiqada eslatma skaneri, inline Tasdiqlash/Bekor.
**Idempotentlik:** `UNIQUE(appointment_id, kind)`; avval `INSERT ... ON CONFLICT DO NOTHING` bilan "egallab" olinadi, keyin yuboriladi; xato bo'lsa egallash o'chiriladi (qayta uriniladi). `FOR UPDATE SKIP LOCKED` + joriy holatni qayta o'qish. Ko'chirishda eski notificationlar o'chiriladi.
**Kamchilik:** egallash va yuborish orasida jarayon o'lsa — eslatma bir martadan kam (at-most-once); dublikatdan yaxshi deb tanlandi.
**Savollar**
1. *Eslatma ikki marta ketmasligini qanday kafolatlaysiz?* — unique constraint + claim-then-send; parallel 6 ta skaner testida 1 ta xabar.
2. *Nega JWT emas, maxsus token?* — Telegram `/start` payload 64 belgi bilan cheklangan.
3. *Bekor qilingan qabulga eslatma ketmasligi?* — skaner joriy holatni qatorni qulflab o'qiydi.

## 6-bosqich. Frontend
**Nima:** Next.js (App Router), TypeScript, Tailwind, TanStack Query; OpenAPI'dan tiplar (`openapi-typescript`).
**Nega:** backend sxemasi o'zgarsa, TypeScript kompilyatsiya xatosi beradi (CI'da sinxronlik tekshiruvi bor).
**Kamchilik:** tokenlar localStorage'da (XSS xavfi; qisqa access + rotatsiya bilan yumshatilgan); avtomatik frontend testlari yo'q.
**Savollar**
1. *TanStack Query nima beradi?* — keshlash, loading/error holatlari, qayta so'rash, mutatsiyadan keyin invalidatsiya.
2. *Slot band bo'lsa UI nima qiladi?* — 409 ni ushlab, mijozni slot tanlashga qaytaradi va ro'yxatni yangilaydi.
3. *Brauzerda topilgan xato?* — `/auth/me` tokensiz ketgan (public yo'l regex'i keng edi) → 401 sikli. Qo'lda brauzer testi buni topdi.

## 7-bosqich. Mustahkamlash
**Nima:** Redis rate limit (global IP, login, OTP, bron), JSON loglar + request_id, prod konfiguratsiya himoyasi (default JWT/OTP/DB parol bo'lsa ishga tushmaydi), nightly `pg_dump` (7 ta saqlanadi), tiklash testi, Locust yuk testi.
**Savollar**
1. *Rate limit Redis yiqilsa?* — fail-open: mavjudlik cheklovdan muhimroq; ogohlantirish log'ga yoziladi.
2. *Backup'ni qanday ishonchli qildingiz?* — tiklash haqiqatan sinaldi: yangi bazaga qayta tiklab, qatorlar soni, constraint va RLS siyosatlari tekshirildi.
3. *Yuk testi natijasi?* — 50 foydalanuvchi, 60 s, 2743 so'rov, 0 xato, p95 38 ms (lokal, taxminiy).

## 8-bosqich. Deploy
**Nima:** prod compose (host port yo'q, healthcheck, xotira limiti, log rotatsiyasi), umumiy edge Caddy uchun `docly.caddy`, `deploy.sh` (preflight, rollback), CI/CD.
**Savollar**
1. *Nega bir nechta loyiha bitta Caddy'ni ulashadi?* — kichik VPS: bitta 80/443, avtomatik TLS; har loyiha o'z snippet'ini beradi.
2. *Rollback?* — oldingi image `:prev` teg bilan saqlanadi; smoke test yiqilsa avtomatik qaytadi.
3. *Nima tekshirilmagan?* — haqiqiy serverda deploy, GitHub Actions, haqiqiy SMS/Telegram (docs/BLOCKERS.md).

## Intervyudan oldin o'zingiz bajaring
- `./scripts/dev.sh` ni ishga tushirib, bron qilib ko'ring; `docs/ARCHITECTURE.md` diagrammalarini o'z so'zingiz bilan tushuntiring.
- `backend/tests/test_booking.py::test_race_decided_by_db_exclusion_constraint` ni o'qing va deadlock hikoyasini ayta oling.
- `backend/tests/test_isolation.py` — klinika A klinika B ma'lumotiga qanday yeta olmasligini ko'rsating.
