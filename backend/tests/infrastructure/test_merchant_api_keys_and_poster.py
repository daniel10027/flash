"""Adaptateurs BE-069 : coffre de clés d'API SHA-256 + rendu d'affiche Pillow."""

from __future__ import annotations

import io

from PIL import Image

from flash.infrastructure.merchant_api_keys import Sha256MerchantApiKeyVault
from flash.infrastructure.merchant_poster import PillowMerchantPosterRenderer


class TestSha256MerchantApiKeyVault:
    def test_generate_is_unique_and_verifiable(self) -> None:
        vault = Sha256MerchantApiKeyVault("pepper")
        a, b = vault.generate(), vault.generate()
        assert a.secret != b.secret
        assert a.secret.startswith(f"mk_{a.prefix}_")
        assert vault.matches(a.secret, a.secret_hash)
        assert not vault.matches(b.secret, a.secret_hash)

    def test_hash_is_salted_by_pepper(self) -> None:
        secret = Sha256MerchantApiKeyVault("p1").generate().secret
        assert Sha256MerchantApiKeyVault("p1").hash(secret) != (
            Sha256MerchantApiKeyVault("p2").hash(secret)
        )

    def test_prefix_of_roundtrips_and_rejects_garbage(self) -> None:
        vault = Sha256MerchantApiKeyVault("p")
        generated = vault.generate()
        assert vault.prefix_of(generated.secret) == generated.prefix
        assert vault.prefix_of("not-a-key") == ""
        assert vault.prefix_of("mk__missingprefix") == ""


class TestPillowMerchantPosterRenderer:
    def test_render_returns_decodable_png(self) -> None:
        png = PillowMerchantPosterRenderer().render(
            merchant_name="Chez Awa", qr_payload="flash://pay?m=abc", category="RESTAURANT"
        )
        image = Image.open(io.BytesIO(png))
        assert image.format == "PNG"
        assert image.size == (1240, 1748)

    def test_render_is_deterministic(self) -> None:
        renderer = PillowMerchantPosterRenderer()
        kw = {"merchant_name": "X", "qr_payload": "flash://pay?m=x", "category": "GEN"}
        assert renderer.render(**kw) == renderer.render(**kw)
