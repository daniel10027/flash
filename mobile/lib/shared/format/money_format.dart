import 'package:intl/intl.dart';

/// Les montants de l'API sont en **unité mineure**. XOF / XAF n'ont pas de
/// décimale (1 minor = 1 franc).
const _zeroDecimal = {'XOF', 'XAF', 'JPY', 'KRW'};

double minorToMajor(int amountMinor, String currency) =>
    _zeroDecimal.contains(currency) ? amountMinor.toDouble() : amountMinor / 100;

String formatMoney(
  int amountMinor,
  String currency, {
  String locale = 'fr',
  bool withSign = false,
}) {
  final digits = _zeroDecimal.contains(currency) ? 0 : 2;
  final fmt = NumberFormat.currency(
    locale: locale,
    name: currency,
    decimalDigits: digits,
    symbol: _symbol(currency),
  );
  final value = minorToMajor(amountMinor, currency);
  final text = fmt.format(value.abs());
  if (withSign) {
    final sign = amountMinor < 0 ? '−' : '+';
    return '$sign $text';
  }
  return amountMinor < 0 ? '− $text' : text;
}

String _symbol(String currency) => switch (currency) {
      'XOF' || 'XAF' => 'F',
      'EUR' => '€',
      'USD' => r'$',
      _ => currency,
    };
