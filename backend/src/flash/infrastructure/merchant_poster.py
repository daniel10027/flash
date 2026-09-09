"""``PillowMerchantPosterRenderer`` — implémentation du port ``MerchantPosterRenderer``.

Rend une affiche PNG (1240 x 1748 ~ A5 @ 210 dpi) : bandeau « Payez avec Flash », nom du
marchand, QR statique, consigne. Aucune police externe : la police bitmap par défaut de
Pillow est agrandie (déterministe, sans dépendance système).
"""

from __future__ import annotations

import io

import qrcode
from PIL import Image, ImageDraw

_W, _H = 1240, 1748
_BORDEAUX = (123, 20, 40)
_INK = (28, 28, 30)
_PAPER = (255, 255, 255)


class PillowMerchantPosterRenderer:
    def render(self, *, merchant_name: str, qr_payload: str, category: str) -> bytes:
        canvas = Image.new("RGB", (_W, _H), _PAPER)
        draw = ImageDraw.Draw(canvas)

        draw.rectangle([0, 0, _W, 210], fill=_BORDEAUX)
        _banner(canvas, "PAYEZ AVEC FLASH", y=70, fill=_PAPER, scale=7)

        _banner(canvas, merchant_name.upper(), y=300, fill=_INK, scale=5)
        _banner(canvas, category.upper(), y=390, fill=_BORDEAUX, scale=3)

        qr_maker = qrcode.QRCode(
            border=2, box_size=20, error_correction=qrcode.constants.ERROR_CORRECT_M
        )
        qr_maker.add_data(qr_payload)
        qr_maker.make(fit=True)
        qr = qr_maker.make_image(fill_color="black", back_color="white").convert("RGB")
        qr = qr.resize((820, 820))
        canvas.paste(qr, ((_W - 820) // 2, 500))

        _banner(canvas, "1. OUVREZ FLASH   2. SCANNEZ   3. PAYEZ", y=1380, fill=_INK, scale=3)
        _banner(canvas, "SANS FRAIS POUR VOUS", y=1450, fill=_BORDEAUX, scale=3)
        draw.rectangle([0, _H - 40, _W, _H], fill=_BORDEAUX)

        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG")
        return buffer.getvalue()


def _banner(
    canvas: Image.Image, text: str, *, y: int, fill: tuple[int, int, int], scale: int
) -> None:
    """Écrit ``text`` centré, agrandi ``scale`` fois à partir de la police bitmap Pillow."""
    measure = ImageDraw.Draw(canvas)
    left, top, right, bottom = (int(v) for v in measure.textbbox((0, 0), text))
    base_w, base_h = right - left, bottom - top
    if base_w == 0 or base_h == 0:  # pragma: no cover - texte vide
        return
    strip = Image.new("RGB", (base_w, base_h), _PAPER)
    ImageDraw.Draw(strip).text((-left, -top), text, fill=fill)
    strip = strip.resize((base_w * scale, base_h * scale), Image.Resampling.NEAREST)
    canvas.paste(strip, ((_W - strip.width) // 2, y))


__all__ = ["PillowMerchantPosterRenderer"]
