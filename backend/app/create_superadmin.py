"""Usage: uv run python -m app.create_superadmin EMAIL (password read from SUPERADMIN_PASSWORD)."""

import asyncio
import os
import sys

from app.core.security import hash_password
from app.db import reset_engine, system_session
from app.models.tables import User


async def main(email: str, password: str) -> None:
    async with system_session() as s:
        s.add(
            User(
                email=email.lower(),
                password_hash=hash_password(password),
                full_name="Superadmin",
                is_superadmin=True,
            )
        )
    await reset_engine()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], os.environ["SUPERADMIN_PASSWORD"]))
