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


@main.command("run-jobs")
def run_jobs() -> None:
    """Exécute une passe des tâches planifiées (à appeler par cron) : expiration des
    opérations en attente + réconciliation des soldes."""
    from flash.application.jobs.agent_commission import PayDueAgentCommissions
    from flash.application.jobs.card_reconcile import ReconcileCardSettlements
    from flash.application.jobs.expire import ExpireStaleOperations
    from flash.application.jobs.merchant_settle import SettleDueMerchants
    from flash.application.jobs.reconcile import ReconcileWalletBalances
    from flash.application.jobs.savings import AccrueSavingsInterest, RunScheduledSavings
    from flash.application.merchants.webhooks import DispatchMerchantWebhooks
    from flash.infrastructure.bank_gateway import SandboxBankGateway
    from flash.infrastructure.config import get_settings
    from flash.infrastructure.merchant_webhooks import HttpMerchantWebhookSender
    from flash.interface.container import build_app_services

    settings = get_settings()
    services = build_app_services(settings)
    bank = SandboxBankGateway(pepper=settings.secret_key)

    expired = ExpireStaleOperations(services=services).execute()
    click.echo(
        f"expiration : {expired.withdrawals_expired} retraits, "
        f"{expired.payment_requests_expired} demandes, "
        f"{expired.merchant_charges_expired} QR marchands"
    )

    contributions = RunScheduledSavings(services=services).execute()
    click.echo(
        f"épargne programmée : {contributions.funded} versés, "
        f"{contributions.skipped} reportés (sur {contributions.checked} échus)"
    )

    interest = AccrueSavingsInterest(services=services).execute()
    click.echo(
        f"intérêts d'épargne : {interest.capitalised_minor} capitalisés "
        f"sur {interest.capitalised_plans} plan(s) ({interest.checked} vérifiés)"
    )

    settlement = SettleDueMerchants(services=services, bank=bank).execute()
    click.echo(
        f"règlements marchands : {settlement.settled} réglés "
        f"({settlement.settled_minor} minor), {settlement.skipped} sans encours, "
        f"{settlement.failed} en échec (sur {settlement.checked} échus)"
    )

    webhooks = DispatchMerchantWebhooks(
        services=services, sender=HttpMerchantWebhookSender()
    ).execute()
    click.echo(
        f"webhooks marchands : {webhooks.delivered} livrés, {webhooks.retried} à retenter, "
        f"{webhooks.exhausted} abandonnés (sur {webhooks.due} échus)"
    )

    commissions = PayDueAgentCommissions(services=services).execute()
    click.echo(
        f"commissions agent : {commissions.paid} versées ({commissions.paid_minor} minor), "
        f"{commissions.skipped} reportées (sur {commissions.checked} éligibles)"
    )

    card_report = ReconcileCardSettlements(services=services).execute()
    if card_report.ok:
        click.echo(f"rapprochement carte : {card_report.checked} autorisations, aucun écart")
    else:
        for cd in card_report.discrepancies:
            click.echo(f"ÉCART carte {cd.authorization_id} : {cd.issue}", err=True)

    report = ReconcileWalletBalances(services=services).execute()
    if report.ok:
        click.echo(f"réconciliation : {report.checked} portefeuilles, aucun écart")
    else:
        for d in report.discrepancies:
            click.echo(
                f"ÉCART wallet {d.wallet_id} : projection {d.projected_minor} "
                f"≠ ledger {d.ledger_minor} (Δ {d.delta_minor})",
                err=True,
            )
        raise SystemExit(1)

    if not card_report.ok:
        raise SystemExit(1)


@main.command("seed")
def seed() -> None:
    """Jeu de données de démo : 2 utilisateurs actifs approvisionnés, 1 agent, 1 marchand."""
    from flash.infrastructure.config import get_settings
    from flash.interface.jobs_seed import seed_demo

    summary = seed_demo(get_settings())
    for line in summary:
        click.echo(line)


@main.group()
def reference() -> None:
    """Référentiel pays / opérateurs."""


@reference.command("seed")
def reference_seed() -> None:
    """Charge le jeu de données pays / opérateurs intégré en base (idempotent)."""
    from flash.infrastructure.db.engine import get_session_factory
    from flash.infrastructure.reference import seed_reference

    count = seed_reference(get_session_factory())
    click.echo(f"Référentiel : {count} pays chargés / mis à jour.")


@main.group()
def openapi() -> None:
    """Spécification OpenAPI."""


@openapi.command("dump")
@click.option("-o", "--output", default="docs/api/openapi.json")
def openapi_dump(output: str) -> None:
    from flash.interface.openapi import dump_spec

    click.echo(f"OpenAPI écrit dans {dump_spec(output)}")


@main.group()
def agent() -> None:
    """Gestion des agents cash."""


@agent.command("enroll")
@click.argument("phone_number")
@click.option("--country", default="CI")
@click.option("--float-cap", "float_cap", type=int, required=True, help="Plafond de float (XOF).")
@click.option("--initial-float", "initial_float", type=int, default=0)
@click.option("--commission-bps", "commission_bps", type=int, default=100)
def agent_enroll(
    phone_number: str,
    country: str,
    float_cap: int,
    initial_float: int,
    commission_bps: int,
) -> None:
    """Fait d'un compte existant un agent cash."""
    from flash.application.cash.operations import EnrollAgent, EnrollAgentCommand
    from flash.domain.shared.identifiers import CountryCode, Msisdn
    from flash.infrastructure.config import get_settings
    from flash.interface.container import build_app_services

    settings = get_settings()
    services = build_app_services(settings)
    msisdn = Msisdn.parse(phone_number, default_country=CountryCode(country.upper()))
    with services.uow() as uow:
        user = uow.users.get_by_msisdn(msisdn)
        if user is None:
            raise click.ClickException(f"Aucun compte pour {msisdn.masked()}.")
        user_id = str(user.id)

    view = EnrollAgent(services=services).execute(
        EnrollAgentCommand(
            user_id=user_id,
            float_cap_minor=float_cap,
            initial_float_minor=initial_float,
            commission_bps=commission_bps,
        )
    )
    click.echo(f"Agent {view.agent_id} — float {view.float_available_minor}/{view.float_cap_minor}")


@main.group()
def merchant() -> None:
    """Gestion des marchands."""


@merchant.command("enroll")
@click.argument("phone_number")
@click.option("--country", default="CI")
@click.option("--name", "display_name", required=True, help="Nom commercial affiché.")
@click.option("--category", default="GENERAL")
@click.option("--fee-bps", "fee_bps", type=int, default=100, help="Commission marchand (bps).")
def merchant_enroll(
    phone_number: str,
    country: str,
    display_name: str,
    category: str,
    fee_bps: int,
) -> None:
    """Fait d'un compte existant un marchand."""
    from flash.application.merchants.operations import EnrollMerchant, EnrollMerchantCommand
    from flash.domain.shared.identifiers import CountryCode, Msisdn
    from flash.infrastructure.config import get_settings
    from flash.interface.container import build_app_services

    settings = get_settings()
    services = build_app_services(settings)
    msisdn = Msisdn.parse(phone_number, default_country=CountryCode(country.upper()))
    with services.uow() as uow:
        user = uow.users.get_by_msisdn(msisdn)
        if user is None:
            raise click.ClickException(f"Aucun compte pour {msisdn.masked()}.")
        user_id = str(user.id)

    view = EnrollMerchant(services=services).execute(
        EnrollMerchantCommand(
            user_id=user_id,
            display_name=display_name,
            category=category,
            fee_bps=fee_bps,
        )
    )
    click.echo(f"Marchand {view.merchant_id} — {view.display_name} (fee {view.fee_bps} bps)")
    click.echo(f"QR statique : {view.static_qr_payload}")


if __name__ == "__main__":
    main()
