import 'package:flutter/material.dart';

import '../../l10n/generated/app_localizations.dart';
import 'amount_field.dart';
import 'primary_button.dart';

/// Demande un montant (unité mineure) dans une feuille. Renvoie `null` si annulé.
Future<int?> promptAmount(
  BuildContext context, {
  required String currency,
  required String title,
}) {
  return showModalBottomSheet<int>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (context) {
      var value = 0;
      return StatefulBuilder(
        builder: (context, setSheet) => Padding(
          padding: EdgeInsets.only(
            left: 20,
            right: 20,
            top: 4,
            bottom: MediaQuery.viewInsetsOf(context).bottom + 20,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(title, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 16),
              AmountField(
                currency: currency,
                valueMinor: value,
                onChanged: (v) => setSheet(() => value = v),
              ),
              const SizedBox(height: 16),
              PrimaryButton(
                label: L10n.of(context).actionContinue,
                onPressed:
                    value > 0 ? () => Navigator.of(context).pop(value) : null,
              ),
              const SizedBox(height: 8),
            ],
          ),
        ),
      );
    },
  );
}
