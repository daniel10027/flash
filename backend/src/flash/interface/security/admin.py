"""``require_admin`` — accès back-office réservé au rôle ``admin``.

Conservé pour compatibilité : délègue à ``require_role`` (BE-062), qui résout la clé
``X-Admin-Key`` vers un rôle. Sans clé ``admin`` configurée, l'accès est refusé (403).
"""

from __future__ import annotations

from flash.interface.security.roles import require_admin

__all__ = ["require_admin"]
