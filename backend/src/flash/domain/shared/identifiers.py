"""Identifiants et value objects transverses : EntityId, CountryCode, Msisdn, IdempotencyKey."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final
from uuid import UUID

# Indicatifs téléphoniques → code pays ISO 3166-1 alpha-2, pour la zone visée au lancement.
# Étendu via le référentiel pays ; cette table sert au parsing hors-ligne du domaine.
_DIALING_CODES: Final[dict[str, str]] = {
    "225": "CI",  # Côte d'Ivoire
    "221": "SN",  # Sénégal
    "223": "ML",  # Mali
    "226": "BF",  # Burkina Faso
    "229": "BJ",  # Bénin
    "228": "TG",  # Togo
    "227": "NE",  # Niger
    "245": "GW",  # Guinée-Bissau
    "237": "CM",  # Cameroun
    "241": "GA",  # Gabon
}
# Trié par longueur décroissante pour un préfixe le plus spécifique d'abord.
_DIALING_CODES_BY_LEN: Final[list[str]] = sorted(_DIALING_CODES, key=len, reverse=True)

_ISO_COUNTRY_RE = re.compile(r"^[A-Z]{2}$")
_E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


class EntityId(str):
    """Identifiant d'entité — un UUID (version 7 en pratique) sérialisé en chaîne.

    Sous-classe ``str`` pour rester trivialement comparable / hashable / sérialisable,
    tout en validant le format à la construction.
    """

    __slots__ = ()

    def __new__(cls, value: str | UUID) -> EntityId:
        text = str(value)
        try:
            UUID(text)
        except ValueError:
            raise ValueError(f"EntityId invalide : {value!r} (UUID attendu)") from None
        return super().__new__(cls, text)


@dataclass(frozen=True, slots=True)
class CountryCode:
    """Code pays ISO 3166-1 alpha-2 (``CI``, ``SN``…)."""

    value: str

    def __post_init__(self) -> None:
        if not _ISO_COUNTRY_RE.match(self.value):
            raise ValueError(f"Code pays invalide : {self.value!r} (ISO 3166-1 alpha-2 attendu)")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class Msisdn:
    """Numéro de téléphone mobile au format E.164 (``+2250700000000``)."""

    value: str

    def __post_init__(self) -> None:
        if not _E164_RE.match(self.value):
            raise ValueError(
                f"Numéro invalide : {self.value!r}. Format E.164 attendu, ex. '+2250700000000'."
            )

    @classmethod
    def parse(cls, raw: str, *, default_country: CountryCode | None = None) -> Msisdn:
        """Normalise une saisie utilisateur en E.164.

        Gère ``+225 07 00 00 00 00``, ``0022507...``, les espaces/points/tirets, et —
        si ``default_country`` est fourni — un numéro national sans indicatif.

        Le numéro national est repris tel quel (séparateurs retirés) et préfixé de
        l'indicatif : le chiffre de préfixe interurbain éventuel fait partie du numéro
        national significatif dans les plans concernés (ex. Côte d'Ivoire : 10 chiffres
        commençant par 0). Aucun zéro de tête n'est retiré.
        """
        cleaned = re.sub(r"[\s.\-()]", "", raw)
        if cleaned.startswith("00"):
            cleaned = "+" + cleaned[2:]
        if cleaned.startswith("+"):
            candidate = cls(cleaned)
            _ = candidate.country_code  # valide que l'indicatif est connu
            return candidate
        if not cleaned.isdigit():
            raise ValueError(f"Numéro invalide : {raw!r}.")
        if default_country is None:
            raise ValueError(f"Numéro sans indicatif international : {raw!r} (préciser le pays).")
        dialing = _dialing_for_country(default_country)
        return cls(f"+{dialing}{cleaned}")

    @property
    def country_code(self) -> CountryCode:
        digits = self.value[1:]
        for prefix in _DIALING_CODES_BY_LEN:
            if digits.startswith(prefix):
                return CountryCode(_DIALING_CODES[prefix])
        raise ValueError(f"Indicatif non reconnu pour {self.value!r}.")

    def masked(self) -> str:
        """Version masquée pour l'affichage et les logs : ``+225070***0000``."""
        return self.value[:8] + "***" + self.value[-4:] if len(self.value) > 12 else self.value

    def __str__(self) -> str:
        return self.value


def _dialing_for_country(country: CountryCode) -> str:
    for dialing, iso in _DIALING_CODES.items():
        if iso == country.value:
            return dialing
    raise ValueError(f"Aucun indicatif connu pour le pays {country.value!r}.")


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    """Clé d'idempotence fournie par le client sur les opérations monétaires."""

    value: str

    def __post_init__(self) -> None:
        if not 8 <= len(self.value) <= 255:
            raise ValueError("La clé d'idempotence doit faire entre 8 et 255 caractères.")
        if any(c.isspace() for c in self.value):
            raise ValueError("La clé d'idempotence ne doit pas contenir d'espace.")

    def scoped(self, *, user_id: str, route: str) -> str:
        """Clé de stockage effective, cloisonnée par utilisateur et par route."""
        return f"idem:{user_id}:{route}:{self.value}"

    def __str__(self) -> str:
        return self.value


__all__ = ["CountryCode", "EntityId", "IdempotencyKey", "Msisdn"]
