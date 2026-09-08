"""Interface en ligne de commande : ``flash …``.

Commandes disponibles aujourd'hui :
- ``flash db upgrade``            applique les migrations Alembic
- ``flash db revision -m "…"``    crée une migration (``--autogenerate`` par défaut)
- ``flash serve``                 lance le serveur de développement Werkzeug
"""

from __future__ import annotations

import click
from alembic import command
from alembic.config import Config

from flash.infrastructure.config import get_settings


def _alembic_config() -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    return cfg


@click.group()
def main() -> None:
    """Outils d'administration de Flash."""


@main.group()
def db() -> None:
    """Migrations de base de données."""


@db.command("upgrade")
@click.argument("revision", default="head")
def db_upgrade(revision: str) -> None:
    command.upgrade(_alembic_config(), revision)


@db.command("downgrade")
@click.argument("revision")
def db_downgrade(revision: str) -> None:
    command.downgrade(_alembic_config(), revision)


@db.command("revision")
@click.option("-m", "--message", required=True)
@click.option("--autogenerate/--empty", default=True)
def db_revision(message: str, autogenerate: bool) -> None:
    command.revision(_alembic_config(), message=message, autogenerate=autogenerate)


@main.command("serve")
@click.option("--host", default="0.0.0.0")
@click.option("--port", default=8000, type=int)
def serve(host: str, port: int) -> None:
    from flash.interface.app import create_app

    create_app().run(host=host, port=port, debug=True, use_reloader=True)


if __name__ == "__main__":
    main()
