# BLOCKERS (items only the owner can provide)

## B1 SMS provider for patient OTP
- Need: an SMS gateway account. `EskizOtpSender` (app/services/otp.py) targets Eskiz (notify.eskiz.uz): POST /api/auth/login, POST /api/message/sms/send.
- Steps: register at Eskiz, get a sender name approved, set `OTP_SENDER=eskiz`, `ESKIZ_EMAIL`, `ESKIZ_PASSWORD`, `ESKIZ_FROM`.
- Status: endpoints/fields were taken from third-party client libraries; the official Postman docs could not be opened, so the real
  sender is **NOT verified against the live API**. Currently faked: `OTP_SENDER=fake` stores the code in Redis (`otp:outbox:<phone>`).
- Safety: in prod the fake sender must not be used (enforced in Phase 7 hardening).
