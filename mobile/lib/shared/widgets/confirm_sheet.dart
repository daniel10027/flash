import 'package:flutter/material.dart';

import '../../l10n/generated/app_localizations.dart';
import 'pin_pad.dart';
import 'primary_button.dart';

/// Feuille de confirmation avant un débit : récapitulatif + friction code
/// secret (le backend n'exige pas le PIN sur ces routes — la session suffit —
/// mais la saisie reste un garde-fou UX).
Future<bool> showConfirmSheet(
  BuildContext context, {
  required String title,
  required Widget summary,
  Future<void> Function()? onConfirm,
}) async {
  final ok = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (context) => _ConfirmBody(
      title: title,
      summary: summary,
      onConfirm: onConfirm,
    ),
  );
  return ok ?? false;
}

class _ConfirmBody extends StatefulWidget {
  const _ConfirmBody({
    required this.title,
    required this.summary,
    this.onConfirm,
  });
  final String title;
  final Widget summary;
  final Future<void> Function()? onConfirm;

  @override
  State<_ConfirmBody> createState() => _ConfirmBodyState();
}

class _ConfirmBodyState extends State<_ConfirmBody> {
  String _pin = '';
  bool _busy = false;

  Future<void> _confirm() async {
    setState(() => _busy = true);
    try {
      await widget.onConfirm?.call();
      if (mounted) Navigator.of(context).pop(true);
    } catch (_) {
      if (mounted) Navigator.of(context).pop(false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 4,
        bottom: MediaQuery.viewInsetsOf(context).bottom + 20,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(widget.title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 12),
          widget.summary,
          const SizedBox(height: 16),
          PinPad(
            length: 4,
            value: _pin,
            onChanged: (v) => setState(() => _pin = v),
          ),
          const SizedBox(height: 12),
          PrimaryButton(
            label: L10n.of(context).actionContinue,
            loading: _busy,
            onPressed: _pin.length == 4 ? _confirm : null,
          ),
          const SizedBox(height: 8),
        ],
      ),
    );
  }
}
