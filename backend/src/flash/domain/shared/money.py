"""Monnaie et devise — value objects immuables.

Règles :
- Les montants sont des **entiers en unité mineure** (jamais de ``float``). Pour le XOF,
  ``exponent = 0`` : l'unité mineure est le franc lui-même.
- Toute opération entre deux ``Money`` de devises différentes lève ``CurrencyMismatch``.
- ``Money`` peut être négatif (utile pour représenter un mouvement) ; les invariants
  "jamais négatif" sont portés par les agrégats (Wallet, etc.), pas par ce VO.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Final

from flash.domain.shared.errors import CurrencyMismatch

# Devises connues au lancement. Le référentiel pays peut en activer d'autres, mais la
# définition (exposant) reste centralisée ici pour éviter toute ambiguïté d'arrondi.
_KNOWN_EXPONENTS: Final[dict[str, int]] = {
    "XOF": 0,  # Franc CFA BCEAO — pas de sous-unité
    "XAF": 0,  # Franc CFA BEAC
    "NGN": 2,
    "GHS": 2,
    "USD": 2,
    "EUR": 2,
}


@dataclass(frozen=True, slots=True, order=False)
class Currency:
    """Devise ISO 4217 avec son exposant décimal (nombre de décimales)."""

    code: str
    exponent: int

    def __post_init__(self) -> None:
        if len(self.code) != 3 or not self.code.isalpha() or not self.code.isupper():
            raise ValueError(f"Code devise invalide : {self.code!r} (attendu ISO 4217, ex. 'XOF')")
        if self.exponent < 0 or self.exponent > 4:
            raise ValueError(f"Exposant de devise hors bornes : {self.exponent}")

    @classmethod
    def of(cls, code: str) -> Currency:
        """Construit une devise connue à partir de son code (``Currency.of('XOF')``)."""
        try:
            return cls(code, _KNOWN_EXPONENTS[code])
        except KeyError:
            raise ValueError(
                f"Devise inconnue : {code!r}. Déclarer son exposant dans money.py."
            ) from None

    @property
    def minor_units_per_unit(self) -> int:
        return int(10**self.exponent)

    def __str__(self) -> str:
        return self.code


XOF: Final = Currency.of("XOF")


@dataclass(frozen=True, slots=True, order=False)
class Money:
    """Montant monétaire : un entier d'unités mineures et une devise."""

    amount_minor: int
    currency: Currency

    def __post_init__(self) -> None:
        if not isinstance(self.amount_minor, int) or isinstance(self.amount_minor, bool):
            raise TypeError("amount_minor doit être un int (unité mineure, jamais un float)")

    # ----- fabriques -------------------------------------------------------------
    @classmethod
    def zero(cls, currency: Currency) -> Money:
        return cls(0, currency)

    @classmethod
    def from_units(cls, units: int | str | Decimal, currency: Currency) -> Money:
        """À partir d'un montant en unité majeure (ex. ``Money.from_units('10.50', EUR)``)."""
        scaled = (Decimal(units) * currency.minor_units_per_unit).to_integral_value(ROUND_HALF_UP)
        return cls(int(scaled), currency)

    # ----- accès ---------------------------------------------------------------
    @property
    def units(self) -> Decimal:
        """Montant en unité majeure, exact (Decimal)."""
        return Decimal(self.amount_minor) / Decimal(self.currency.minor_units_per_unit)

    @property
    def is_zero(self) -> bool:
        return self.amount_minor == 0

    @property
    def is_negative(self) -> bool:
        return self.amount_minor < 0

    @property
    def is_positive(self) -> bool:
        return self.amount_minor > 0

    # ----- arithmétique ------------------------------------------------------------
    def _check_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatch(self.currency.code, other.currency.code)

    def __add__(self, other: Money) -> Money:
        self._check_same_currency(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check_same_currency(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount_minor, self.currency)

    def __mul__(self, factor: int) -> Money:
        if not isinstance(factor, int) or isinstance(factor, bool):
            raise TypeError("Money ne peut être multiplié que par un int")
        return Money(self.amount_minor * factor, self.currency)

    __rmul__ = __mul__

    def percentage(self, bps: int, *, rounding: str = ROUND_HALF_UP) -> Money:
        """Applique un pourcentage exprimé en points de base (100 bps = 1 %).

        L'arrondi porte sur l'unité mineure. ``ROUND_FLOOR`` disponible pour les cas où
        l'on ne veut jamais dépasser le montant de référence.
        """
        if bps < 0:
            raise ValueError("bps ne peut pas être négatif")
        raw = Decimal(self.amount_minor) * Decimal(bps) / Decimal(10_000)
        return Money(int(raw.to_integral_value(rounding)), self.currency)

    # ----- comparaisons ----------------------------------------------------------
    def __lt__(self, other: Money) -> bool:
        self._check_same_currency(other)
        return self.amount_minor < other.amount_minor

    def __le__(self, other: Money) -> bool:
        self._check_same_currency(other)
        return self.amount_minor <= other.amount_minor

    def __gt__(self, other: Money) -> bool:
        self._check_same_currency(other)
        return self.amount_minor > other.amount_minor

    def __ge__(self, other: Money) -> bool:
        self._check_same_currency(other)
        return self.amount_minor >= other.amount_minor

    # ----- divers -------------------------------------------------------------
    def with_amount(self, amount_minor: int) -> Money:
        return Money(amount_minor, self.currency)

    def __str__(self) -> str:
        if self.currency.exponent == 0:
            return f"{self.amount_minor} {self.currency.code}"
        q = Decimal(1).scaleb(-self.currency.exponent)
        return f"{self.units.quantize(q, ROUND_FLOOR)} {self.currency.code}"


__all__ = ["XOF", "Currency", "Money"]
