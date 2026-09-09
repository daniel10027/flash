"""Blueprint ``notifications`` — journal in-app (BE-040) + flux SSE (BE-042)."""

from __future__ import annotations

import json
from collections.abc import Iterator

from flask import Blueprint, Response, jsonify, request

from flash.application.notifications.model import Notification
from flash.application.notifications.queries import (
    ListNotifications,
    ListNotificationsCommand,
    MarkAllNotificationsRead,
    MarkAllNotificationsReadCommand,
    MarkNotificationRead,
    MarkNotificationReadCommand,
)
from flash.application.notifications.stream import (
    NotificationStream,
    StreamNotificationsCommand,
)
from flash.interface.container import deps
from flash.interface.openapi import document
from flash.interface.security.auth import current_principal, require_auth

bp = Blueprint("notifications", __name__, url_prefix="/v1/notifications")


def _sse_frame(notification: Notification) -> str:
    payload = json.dumps(notification.to_dict(), ensure_ascii=False)
    return f"id: {notification.id}\nevent: notification\ndata: {payload}\n\n"


@bp.get("")
@require_auth
@document(summary="Journal des notifications (paginé par curseur)", tags=["notifications"])
def list_notifications() -> tuple[Response, int]:
    try:
        limit = int(request.args.get("limit", 20))
    except ValueError:
        limit = 20
    page = ListNotifications(notifications=deps().notifications).execute(
        ListNotificationsCommand(
            user_id=str(current_principal().user_id),
            unread_only=request.args.get("unread") in ("1", "true", "yes"),
            limit=limit,
            cursor=request.args.get("cursor"),
        )
    )
    return jsonify(page.to_dict()), 200


@bp.post("/<notification_id>/read")
@require_auth
@document(summary="Marquer une notification comme lue", tags=["notifications"])
def mark_read(notification_id: str) -> tuple[Response, int]:
    updated = MarkNotificationRead(notifications=deps().notifications).execute(
        MarkNotificationReadCommand(
            user_id=str(current_principal().user_id), notification_id=notification_id
        )
    )
    return jsonify({"updated": updated}), 200


@bp.post("/read-all")
@require_auth
@document(summary="Marquer toutes les notifications comme lues", tags=["notifications"])
def mark_all_read() -> tuple[Response, int]:
    count = MarkAllNotificationsRead(notifications=deps().notifications).execute(
        MarkAllNotificationsReadCommand(user_id=str(current_principal().user_id))
    )
    return jsonify({"updated": count}), 200


@bp.get("/stream")
@require_auth
@document(
    summary="Flux temps réel des notifications (SSE)",
    tags=["notifications"],
    secured=True,
)
def stream() -> Response:
    user_id = str(current_principal().user_id)
    last_event_id = request.headers.get("Last-Event-ID") or request.args.get("last_event_id")
    source = NotificationStream(notifications=deps().notifications, bus=deps().notification_bus)

    def frames() -> Iterator[str]:
        yield "retry: 3000\n\n"
        for item in source.events(
            StreamNotificationsCommand(user_id=user_id, last_event_id=last_event_id)
        ):
            yield ": keep-alive\n\n" if item is None else _sse_frame(item)

    response = Response(frames(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Connection"] = "keep-alive"
    return response


__all__ = ["bp"]
