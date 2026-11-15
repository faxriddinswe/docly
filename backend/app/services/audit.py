import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import AuditLog


async def record(
    session: AsyncSession,
    *,
    clinic_id: uuid.UUID | None,
    actor_user_id: uuid.UUID | None,
    action: str,
    entity: str,
    entity_id: uuid.UUID | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    """Append-only audit trail; written in the same transaction as the mutation."""
    session.add(
        AuditLog(
            clinic_id=clinic_id,
            actor_user_id=actor_user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            data=data or {},
        )
    )
    await session.flush()
