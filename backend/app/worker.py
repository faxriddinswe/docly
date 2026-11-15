"""ARQ worker: `arq app.worker.WorkerSettings`. Runs the reminder scan every minute."""

import logging
from typing import Any

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.services.reminders import run_reminder_scan
from app.services.telegram import AiogramTransport, Transport

log = logging.getLogger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    setup_logging()
    token = get_settings().telegram_bot_token
    ctx["transport"] = AiogramTransport(token) if token else None
    if ctx["transport"] is None:
        log.warning("TELEGRAM_BOT_TOKEN not set: reminders are skipped")


async def shutdown(ctx: dict[str, Any]) -> None:
    transport = ctx.get("transport")
    if isinstance(transport, AiogramTransport):
        await transport.close()


async def scan_reminders(ctx: dict[str, Any]) -> int:
    transport: Transport | None = ctx.get("transport")
    if transport is None:
        return 0
    sent = await run_reminder_scan(transport)
    if sent:
        log.info("reminders sent: %d", sent)
    return sent


class WorkerSettings:
    functions = [scan_reminders]
    cron_jobs = [cron(scan_reminders, minute=set(range(60)), run_at_startup=True)]
    on_startup = startup
    on_shutdown = shutdown
    health_check_interval = 30  # `arq --check` (docker healthcheck) reads this key
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
