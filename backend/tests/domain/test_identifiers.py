"""Tests des identifiants et VO transverses (BE-004)."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.domain.shared.identifiers import CountryCode, EntityId, IdempotencyKey, Msisdn


class TestEntityId:
    def test_accepts_uuid_object_and_string(self) -> None:
        u = UUID(int=42)
        assert EntityId(u) == str(u)
        assert EntityId(str(u)) == str(u)

    def test_is_str_subclass(self) -> None:
        eid = EntityId(UUID(int=1))
        assert isinstance(eid, str)

    def test_rejects_non_uuid(self) -> None:
        with pytest.raises(ValueError):
            EntityId("not-a-uuid")


class TestCountryCode:
    @pytest.mark.parametrize("code", ["CI", "SN", "ML"])
    def test_valid(self, code: str) -> None:
        assert str(CountryCode(code)) == code

    @pytest.mark.parametrize("code", ["ci", "CIV", "C1", "France"])
    def test_invalid(self, code: str) -> None:
        with pytest.raises(ValueError):
            CountryCode(code)


class TestMsisdn:
    def test_valid_e164(self) -> None:
        assert Msisdn("+2250700000000").value == "+2250700000000"

    def test_country_code_from_dialing_prefix(self) -> None:
        assert Msisdn("+2250700000000").country_code == CountryCode("CI")
        assert Msisdn("+221770000000").country_code == CountryCode("SN")

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("+225 07 00 00 00 00", "+2250700000000"),
            ("00225-07.00.00.00.00", "+2250700000000"),
            ("+225 (07) 0000-0000", "+2250700000000"),
        ],
    )
    def test_parse_normalises_separators_and_00_prefix(self, raw: str, expected: str) -> None:
        assert Msisdn.parse(raw).value == expected

    def test_parse_national_number_with_default_country(self) -> None:
        parsed = Msisdn.parse("0700000000", default_country=CountryCode("CI"))
        assert parsed.value == "+2250700000000"

    def test_parse_national_number_without_country_rejected(self) -> None:
        with pytest.raises(ValueError, match="sans indicatif"):
            Msisdn.parse("0700000000")

    def test_parse_non_numeric_national_input_rejected(self) -> None:
        with pytest.raises(ValueError, match="Numéro invalide"):
            Msisdn.parse("07ABC0000", default_country=CountryCode("CI"))

    def test_parse_country_without_known_dialing_code_rejected(self) -> None:
        with pytest.raises(ValueError, match="Aucun indicatif connu"):
            Msisdn.parse("0700000000", default_country=CountryCode("US"))

    def test_str_returns_e164(self) -> None:
        assert str(Msisdn("+2250700000000")) == "+2250700000000"

    def test_masked_short_number_unchanged(self) -> None:
        # Numéro E.164 minimal (7 chiffres) : pas assez long pour être masqué.
        assert Msisdn("+2250700").masked() == "+2250700"

    def test_parse_unknown_dialing_code_rejected(self) -> None:
        with pytest.raises(ValueError, match="Indicatif non reconnu"):
            Msisdn.parse("+9990700000000")

    @pytest.mark.parametrize("bad", ["0700000000", "+225", "+0700000000", "225070000"])
    def test_invalid_e164_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError):
            Msisdn(bad)

    def test_masked_hides_middle(self) -> None:
        masked = Msisdn("+2250701020304").masked()
        assert masked.startswith("+225") and masked.endswith("0304") and "***" in masked

    def test_is_value_object(self) -> None:
        assert Msisdn("+2250700000000") == Msisdn("+2250700000000")
        assert hash(Msisdn("+2250700000000")) == hash(Msisdn("+2250700000000"))


class TestIdempotencyKey:
    def test_valid(self) -> None:
        assert IdempotencyKey("abc12345").value == "abc12345"

    @pytest.mark.parametrize("bad", ["short", "x" * 256, "has space in it"])
    def test_invalid(self, bad: str) -> None:
        with pytest.raises(ValueError):
            IdempotencyKey(bad)

    def test_scoped_key_is_partitioned(self) -> None:
        key = IdempotencyKey("abc12345")
        scoped = key.scoped(user_id="u-1", route="POST /v1/transfers")
        assert scoped == "idem:u-1:POST /v1/transfers:abc12345"

    def test_str_returns_raw_value(self) -> None:
        assert str(IdempotencyKey("abc12345")) == "abc12345"
