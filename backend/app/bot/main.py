"""Telegram bot process (long polling): `python -m app.bot.main`. Needs TELEGRAM_BOT_TOKEN (see BLOCKERS)."""

import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.services import telegram_flow

dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message, command: CommandObject) -> None:
    if not command.args:
        await message.answer("Salom! Eslatmalarni olish uchun klinika saytidagi havoladan foydalaning.")
        return
    await message.answer(await telegram_flow.handle_start(command.args, message.chat.id))


@dp.callback_query(F.data)
async def callback(query: CallbackQuery) -> None:
    if query.message is None or query.data is None:
        return
    text = await telegram_flow.handle_callback(query.data, query.message.chat.id)
    await query.answer(text, show_alert=True)


async def main() -> None:
    setup_logging()
    token = get_settings().telegram_bot_token
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set (see docs/BLOCKERS.md B2)")
    bot = Bot(token=token)
    logging.getLogger(__name__).info("bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
