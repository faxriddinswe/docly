"""Telegram transport interface. Tests use FakeTransport; production uses AiogramTransport."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Button:
    label: str
    callback_data: str


class Transport(Protocol):
    async def send_message(self, chat_id: int, text: str, buttons: list[Button] | None = None) -> None: ...


@dataclass
class SentMessage:
    chat_id: int
    text: str
    buttons: list[Button] | None


@dataclass
class FakeTransport:
    sent: list[SentMessage] = field(default_factory=list)
    fail_next: bool = False

    async def send_message(self, chat_id: int, text: str, buttons: list[Button] | None = None) -> None:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("simulated telegram outage")
        self.sent.append(SentMessage(chat_id, text, buttons))


class AiogramTransport:
    def __init__(self, token: str) -> None:
        from aiogram import Bot

        self.bot = Bot(token=token)

    async def send_message(self, chat_id: int, text: str, buttons: list[Button] | None = None) -> None:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

        markup = None
        if buttons:
            markup = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=b.label, callback_data=b.callback_data) for b in buttons]]
            )
        await self.bot.send_message(chat_id, text, reply_markup=markup)

    async def close(self) -> None:
        await self.bot.session.close()
