import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../../shared/widgets/amount_field.dart';
import '../../shared/widgets/app_snackbar.dart';
import '../../shared/widgets/primary_button.dart';
import '../wallet/wallet_providers.dart';

/// MOB-024 — retrait / dépôt vers un compte opérateur mobile money.
class OperatorPage extends ConsumerStatefulWidget {
  const OperatorPage({super.key});

  @override
  ConsumerState<OperatorPage> createState() => _OperatorPageState();
}

class _OperatorPageState extends ConsumerState<OperatorPage> {
  static const _operators = ['MTN', 'ORANGE', 'MOOV', 'WAVE'];
  String _operator = 'MTN';
  bool _payout =
      true; // true = envoyer vers l'opérateur, false = recharger Flash
  final _phone = TextEditingController();
  int _amount = 0;
  bool _busy = false;

  @override
  void dispose() {
    _phone.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() => _busy = true);
    try {
      await ref.read(apiClientProvider).postJson(
        '/v1/operators/${_operator.toLowerCase()}/${_payout ? 'payout' : 'topup'}',
        body: {'phone_number': _phone.text.trim(), 'amount_minor': _amount},
      );
      if (mounted) {
        AppSnack.success(context, 'Opération en cours de traitement.');
        setState(() => _amount = 0);
      }
      refreshDashboard(ref);
    } catch (e) {
      if (mounted) AppSnack.error(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final currency =
        ref.watch(primaryWalletProvider).valueOrNull?.currency ?? 'XOF';
    return Scaffold(
      appBar: AppBar(title: const Text('Compte opérateur')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            SegmentedButton<bool>(
              segments: const [
                ButtonSegment(value: true, label: Text('Vers opérateur')),
                ButtonSegment(value: false, label: Text('Recharger Flash')),
              ],
              selected: {_payout},
              onSelectionChanged: (s) => setState(() => _payout = s.first),
            ),
            const SizedBox(height: 16),
            Wrap(
              spacing: 8,
              children: [
                for (final o in _operators)
                  ChoiceChip(
                    label: Text(o),
                    selected: _operator == o,
                    onSelected: (_) => setState(() => _operator = o),
                  ),
              ],
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _phone,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(labelText: 'Numéro opérateur'),
            ),
            const SizedBox(height: 20),
            AmountField(
              currency: currency,
              valueMinor: _amount,
              onChanged: (v) => setState(() => _amount = v),
            ),
            const SizedBox(height: 24),
            PrimaryButton(
              label: 'Valider',
              loading: _busy,
              onPressed:
                  _amount > 0 && _phone.text.trim().isNotEmpty ? _submit : null,
            ),
            const SizedBox(height: 12),
            Text(
              'Le statut final arrive par notification (traitement asynchrone).',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}
