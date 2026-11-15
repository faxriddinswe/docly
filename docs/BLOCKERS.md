# BLOCKERS (items only the owner can provide)

## B1 SMS provider for patient OTP
- Need: an SMS gateway account. `EskizOtpSender` (app/services/otp.py) targets Eskiz (notify.eskiz.uz): POST /api/auth/login, POST /api/message/sms/send.
- Steps: register at Eskiz, get a sender name approved, set `OTP_SENDER=eskiz`, `ESKIZ_EMAIL`, `ESKIZ_PASSWORD`, `ESKIZ_FROM`.
- Status: endpoints/fields were taken from third-party client libraries; the official Postman docs could not be opened, so the real
  sender is **NOT verified against the live API**. Currently faked: `OTP_SENDER=fake` stores the code in Redis (`otp:outbox:<phone>`).
- Safety: in prod the fake sender must not be used (enforced in Phase 7 hardening).

## B2 Telegram bot token
- Need: a bot from @BotFather. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_BOT_USERNAME` (without @) in the environment.
- Run: `python -m app.bot.main` (long polling) and the ARQ worker (`arq app.worker.WorkerSettings`).
- Status: all logic is tested with FakeTransport, and the ARQ worker is tested against real Redis. `AiogramTransport` and the aiogram
  handlers in app/bot/main.py are **not exercised against the real Telegram API**. Without a token the worker skips reminders
  (logs a warning) and booking responses carry `telegram_link: null`.

## B3 Production server, domain and DNS (deployment)
- Need: a VPS reachable by SSH, a domain, and a DNS A record `SUBDOMAIN.BASE_DOMAIN -> server IP`.
- Steps: copy `.env.deploy.example` to `.env.deploy` (gitignored) and fill `DEPLOY_HOST, DEPLOY_USER, SSH_KEY_PATH, BASE_DOMAIN, SUBDOMAIN`;
  the deploy user must be in the `docker` group and own/write `/opt` (or an owner must pre-create `/opt/docly`). Then run `scripts/deploy.sh`.
  For CI/CD set GitHub secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY` and repository variables `BASE_DOMAIN`, `SUBDOMAIN`.
- Status: NOT deployed. Everything else is built; the production stack was verified locally (see docs/DEPLOY.md). `deploy.sh` remote steps are verified
  only in `DRY_RUN=1` mode (printed commands reviewed), never against a real server.

## B4 Git remote
- No git remote is configured, so nothing was pushed (protocol A9). To publish: `git remote add origin <url> && git push -u origin main`; CI then runs on GitHub.
