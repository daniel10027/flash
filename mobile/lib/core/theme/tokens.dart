import 'package:flutter/material.dart';

/// Palette Flash — miroir de `design/tokens.json` (thème bordeaux).
/// Source de vérité partagée avec le web.
abstract final class FlashColors {
  static const brand50 = Color(0xFFFBEEF0);
  static const brand100 = Color(0xFFF4CCD2);
  static const brand200 = Color(0xFFE79AA6);
  static const brand300 = Color(0xFFD76678);
  static const brand400 = Color(0xFFC23D54);
  static const brand500 = Color(0xFF8C1D33); // couleur de marque
  static const brand600 = Color(0xFF7A1A2D);
  static const brand700 = Color(0xFF621525);
  static const brand800 = Color(0xFF4B101C);
  static const brand900 = Color(0xFF360B14);

  static const accent300 = Color(0xFF7CD4C0);
  static const accent500 = Color(0xFF12A594);
  static const accent700 = Color(0xFF0C7A6D);

  static const neutral0 = Color(0xFFFFFFFF);
  static const neutral50 = Color(0xFFF7F7F8);
  static const neutral100 = Color(0xFFEDEDF0);
  static const neutral200 = Color(0xFFDCDCE1);
  static const neutral300 = Color(0xFFC2C2CB);
  static const neutral400 = Color(0xFF9A9AA6);
  static const neutral500 = Color(0xFF727282);
  static const neutral600 = Color(0xFF54545F);
  static const neutral700 = Color(0xFF3C3C45);
  static const neutral800 = Color(0xFF26262C);
  static const neutral900 = Color(0xFF161619);

  static const successFg = Color(0xFF0C7A3F);
  static const successBg = Color(0xFFE6F4EA);
  static const warningFg = Color(0xFF8A5A00);
  static const warningBg = Color(0xFFFBF0DC);
  static const dangerFg = Color(0xFFA4152B);
  static const dangerBg = Color(0xFFFBE9EC);
}

/// Rayons de coins (design/tokens.json → radius).
abstract final class FlashRadii {
  static const sm = 6.0;
  static const md = 10.0;
  static const lg = 16.0;
  static const xl = 24.0;
  static const full = 999.0;
}

/// Échelle d'espacement (base 4).
abstract final class Gap {
  static const xs = SizedBox(width: 4, height: 4);
  static const sm = SizedBox(width: 8, height: 8);
  static const md = SizedBox(width: 12, height: 12);
  static const lg = SizedBox(width: 16, height: 16);
  static const xl = SizedBox(width: 24, height: 24);
  static const xxl = SizedBox(width: 32, height: 32);

  static const d1 = 4.0;
  static const d2 = 8.0;
  static const d3 = 12.0;
  static const d4 = 16.0;
  static const d5 = 24.0;
  static const d6 = 32.0;
}
