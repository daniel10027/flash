"""Blueprint ``notifications`` — journal in-app (BE-040). Le flux SSE arrive en BE-041."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from flash.application.notifications.queries import (
    ListNotifications,
    ListNotificationsCommand,
    MarkAllNotificationsRead,
    MarkAllNotificationsReadCommand,
    MarkNotificationRead,
    MarkNotificationReadCommand,
)
from flash.interface.container import deps
from flash.interface.openapi import document
from flash.interface.security.auth import current_principal, require_auth

bp = Blueprint("notifications", __name__, url_prefix="/v1/notifications")


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


__all__ = ["bp"]
