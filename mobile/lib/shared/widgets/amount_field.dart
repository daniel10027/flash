import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../format/money_format.dart';

const _p2pFeeBps = 80; // 0,8 %

/// Grande saisie de montant, style « caisse ». Optionnellement, aperçu des
/// frais 0,8 % + total débité.
class AmountField extends StatelessWidget {
  const AmountField({
    required this.currency,
    required this.valueMinor,
    required this.onChanged,
    this.showFee = false,
    this.autofocus = true,
    super.key,
  });

  final String currency;
  final int valueMinor;
  final ValueChanged<int> onChanged;
  final bool showFee;
  final bool autofocus;

  bool get _zeroDecimal => currency == 'XOF' || currency == 'XAF';

  @override
  Widget build(BuildContext context) {
    final fee = showFee ? (valueMinor * _p2pFeeBps / 10000).ceil() : 0;
    final text = valueMinor == 0
        ? ''
        : _zeroDecimal
            ? '$valueMinor'
            : (valueMinor / 100).toStringAsFixed(2);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          autofocus: autofocus,
          controller: TextEditingController(text: text)
            ..selection = TextSelection.collapsed(offset: text.length),
          keyboardType:
              TextInputType.numberWithOptions(decimal: !_zeroDecimal),
          inputFormatters: [
            FilteringTextInputFormatter.allow(RegExp(r'[0-9.,]')),
          ],
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.displaySmall?.copyWith(
                fontWeight: FontWeight.w700,
                fontFeatures: const [FontFeature.tabularFigures()],
              ),
          decoration: InputDecoration(
            hintText: '0',
            suffixText: currency,
            border: InputBorder.none,
            enabledBorder: InputBorder.none,
            focusedBorder: InputBorder.none,
            filled: false,
          ),
          onChanged: (raw) {
            final n = double.tryParse(raw.replaceAll(',', '.')) ?? 0;
            onChanged(_zeroDecimal ? n.round() : (n * 100).round());
          },
        ),
        if (showFee && valueMinor > 0) ...[
          const SizedBox(height: 16),
          _FeeRow(label: 'Frais (0,8 %)', value: formatMoney(fee, currency)),
          const SizedBox(height: 4),
          _FeeRow(
            label: 'Total débité',
            value: formatMoney(valueMinor + fee, currency),
            strong: true,
          ),
        ],
      ],
    );
  }
}

class _FeeRow extends StatelessWidget {
  const _FeeRow({required this.label, required this.value, this.strong = false});
  final String label;
  final String value;
  final bool strong;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context).textTheme.bodyMedium;
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: t?.copyWith(color: Theme.of(context).hintColor)),
        Text(
          value,
          style: t?.copyWith(
            fontWeight: strong ? FontWeight.w700 : FontWeight.w500,
          ),
        ),
      ],
    );
  }
}
