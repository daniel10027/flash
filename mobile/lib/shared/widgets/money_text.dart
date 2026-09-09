import 'package:flutter/material.dart';

import '../format/money_format.dart';

/// Affiche un montant en unité mineure, formaté selon la devise.
class MoneyText extends StatelessWidget {
  const MoneyText(
    this.amountMinor,
    this.currency, {
    this.style,
    this.withSign = false,
    this.hidden = false,
    super.key,
  });

  final int amountMinor;
  final String currency;
  final TextStyle? style;
  final bool withSign;
  final bool hidden;

  @override
  Widget build(BuildContext context) {
    final text = hidden
        ? '••••••'
        : formatMoney(amountMinor, currency, withSign: withSign);
    Color? color;
    if (withSign && !hidden) {
      color = amountMinor < 0
          ? Theme.of(context).colorScheme.onSurface
          : Theme.of(context).colorScheme.secondary;
    }
    return Text(
      text,
      style: (style ?? Theme.of(context).textTheme.titleMedium)?.copyWith(
        color: color,
        fontFeatures: const [FontFeature.tabularFigures()],
      ),
    );
  }
}
