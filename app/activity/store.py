from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.activity.models import ActivityLog


def _clip(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    return value[:limit]


@dataclass(frozen=True)
class ActivityRecord:
    event_id: str
    event_type: str
    user_id: str | None
    session_id: str | None
    visitor_id: str | None
    request_id: str | None
    ip_address: str | None
    method: str | None
    path: str
    status_code: int | None
    duration_ms: float | None
    referrer: str | None
    user_agent: str | None
    target: str | None
    metadata_json: dict[str, object] | None
    created_at: datetime


class ActivityStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def record_event(
        self,
        *,
        event_type: str,
        path: str,
        user_id: str | None = None,
        session_id: str | None = None,
        visitor_id: str | None = None,
        request_id: str | None = None,
        ip_address: str | None = None,
        method: str | None = None,
        status_code: int | None = None,
        duration_ms: float | None = None,
        referrer: str | None = None,
        user_agent: str | None = None,
        target: str | None = None,
        metadata_json: dict[str, object] | None = None,
    ) -> str:
        event = ActivityLog(
            event_type=_clip(event_type, 32) or "unknown",
            user_id=_clip(user_id, 36),
            session_id=_clip(session_id, 64),
            visitor_id=_clip(visitor_id, 64),
            request_id=_clip(request_id, 64),
            ip_address=_clip(ip_address, 64),
            method=_clip(method, 12),
            path=_clip(path, 2048) or "/",
            status_code=status_code,
            duration_ms=duration_ms,
            referrer=_clip(referrer, 2048),
            user_agent=_clip(user_agent, 512),
            target=_clip(target, 512),
            metadata_json=metadata_json,
        )
        async with self.sessions() as session:
            session.add(event)
            await session.commit()
        return event.event_id

    async def list_events(
        self,
        *,
        event_type: str | None = None,
        path_contains: str | None = None,
        limit: int = 100,
    ) -> list[ActivityRecord]:
        statement = select(ActivityLog).order_by(ActivityLog.created_at.desc()).limit(limit)
        if event_type:
            statement = statement.where(ActivityLog.event_type == event_type)
        if path_contains:
            statement = statement.where(ActivityLog.path.ilike(f"%{path_contains[:200]}%"))

        async with self.sessions() as session:
            events = (await session.scalars(statement)).all()

        return [
            ActivityRecord(
                event_id=event.event_id,
                event_type=event.event_type,
                user_id=event.user_id,
                session_id=event.session_id,
                visitor_id=event.visitor_id,
                request_id=event.request_id,
                ip_address=event.ip_address,
                method=event.method,
                path=event.path,
                status_code=event.status_code,
                duration_ms=event.duration_ms,
                referrer=event.referrer,
                user_agent=event.user_agent,
                target=event.target,
                metadata_json=event.metadata_json,
                created_at=event.created_at,
            )
            for event in events
        ]
