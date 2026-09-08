"""Dépôt SQLAlchemy des notifications in-app.

Hors Unit of Work métier : la livraison des notifications est un effet best-effort qui
survient **après** le commit de l'opération. Chaque écriture / lecture ouvre sa propre
courte session.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from flash.application.notifications.model import Notification, NotificationKind
from flash.infrastructure.db.models import NotificationModel


def _to_domain(model: NotificationModel) -> Notification:
    return Notification(
        id=model.id,
        user_id=model.user_id,
        kind=NotificationKind(model.kind),
        title=model.title,
        body=model.body,
        created_at=model.created_at,
        data=dict(model.data or {}),
        read_at=model.read_at,
    )


class SqlAlchemyNotificationRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def add(self, notification: Notification) -> None:
        with self._session_factory() as session:
            session.add(
                NotificationModel(
                    id=notification.id,
                    user_id=notification.user_id,
                    kind=notification.kind.value,
                    title=notification.title,
                    body=notification.body,
                    data=dict(notification.data),
                    created_at=notification.created_at,
                    read_at=notification.read_at,
                )
            )
            session.commit()

    def get(self, notification_id: str) -> Notification | None:
        with self._session_factory() as session:
            model = session.get(NotificationModel, notification_id)
            return _to_domain(model) if model is not None else None

    def list_for_user(
        self,
        user_id: str,
        *,
        unread_only: bool = False,
        limit: int = 20,
        before: str | None = None,
    ) -> list[Notification]:
        stmt = select(NotificationModel).where(NotificationModel.user_id == user_id)
        if unread_only:
            stmt = stmt.where(NotificationModel.read_at.is_(None))
        if before:
            stmt = stmt.where(NotificationModel.id < before)
        stmt = stmt.order_by(NotificationModel.id.desc()).limit(limit)
        with self._session_factory() as session:
            return [_to_domain(m) for m in session.scalars(stmt)]

    def count_unread(self, user_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(NotificationModel)
            .where(
                NotificationModel.user_id == user_id,
                NotificationModel.read_at.is_(None),
            )
        )
        with self._session_factory() as session:
            return int(session.scalar(stmt) or 0)

    def mark_read(self, user_id: str, notification_id: str) -> bool:
        stmt = (
            update(NotificationModel)
            .where(
                NotificationModel.id == notification_id,
                NotificationModel.user_id == user_id,
                NotificationModel.read_at.is_(None),
            )
            .values(read_at=datetime.now(UTC))
        )
        with self._session_factory() as session:
            rowcount = session.execute(stmt).rowcount  # type: ignore[attr-defined]
            session.commit()
            return bool(rowcount and rowcount > 0)

    def mark_all_read(self, user_id: str) -> int:
        stmt = (
            update(NotificationModel)
            .where(
                NotificationModel.user_id == user_id,
                NotificationModel.read_at.is_(None),
            )
            .values(read_at=datetime.now(UTC))
        )
        with self._session_factory() as session:
            rowcount = session.execute(stmt).rowcount  # type: ignore[attr-defined]
            session.commit()
            return int(rowcount or 0)


__all__ = ["SqlAlchemyNotificationRepository"]
