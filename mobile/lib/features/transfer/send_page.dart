import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../../l10n/generated/app_localizations.dart';
import '../../shared/format/money_format.dart';
import '../../shared/widgets/amount_field.dart';
import '../../shared/widgets/app_snackbar.dart';
import '../../shared/widgets/confirm_sheet.dart';
import '../../shared/widgets/primary_button.dart';
import '../../shared/widgets/receipt_view.dart';
import '../wallet/wallet_providers.dart';

class SendPage extends ConsumerStatefulWidget {
  const SendPage({super.key});

  @override
  ConsumerState<SendPage> createState() => _SendPageState();
}

class _SendPageState extends ConsumerState<SendPage> {
  final _phone = TextEditingController();
  int _amount = 0;
  Map<String, dynamic>? _receipt;

  @override
  void dispose() {
    _phone.dispose();
    super.dispose();
  }

  Future<void> _send(String currency) async {
    try {
      final r = await ref.read(apiClientProvider).postJson(
        '/v1/transfers',
        body: {
          'recipient_phone_number': _phone.text.trim(),
          'amount_minor': _amount,
        },
      );
      if (mounted) setState(() => _receipt = r);
      refreshDashboard(ref);
    } catch (e) {
      if (mounted) AppSnack.error(context, e);
      rethrow;
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = L10n.of(context);
    final wallet = ref.watch(primaryWalletProvider).valueOrNull;
    final currency = wallet?.currency ?? 'XOF';

    if (_receipt != null) {
      return Scaffold(
        appBar: AppBar(title: Text(l.quickSend)),
        body: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            children: [
              ReceiptView(data: _receipt!, title: 'Transfert effectué'),
              const SizedBox(height: 24),
              PrimaryButton(
                label: 'Nouveau transfert',
                onPressed: () => setState(() {
                  _receipt = null;
                  _amount = 0;
                  _phone.clear();
                }),
              ),
            ],
          ),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(title: Text(l.quickSend)),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            TextField(
              controller: _phone,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(
                labelText: 'Numéro du destinataire',
                hintText: '+225…',
                prefixIcon: Icon(Icons.person_outline),
              ),
              onChanged: (_) => setState(() {}),
            ),
            const SizedBox(height: 24),
            AmountField(
              currency: currency,
              valueMinor: _amount,
              showFee: true,
              onChanged: (v) => setState(() => _amount = v),
            ),
            const SizedBox(height: 24),
            PrimaryButton(
              label: l.actionContinue,
              onPressed: _phone.text.trim().isNotEmpty && _amount > 0
                  ? () async {
                      final ok = await showConfirmSheet(
                        context,
                        title: 'Confirmer le transfert',
                        summary: Text(
                          '${formatMoney(_amount, currency)} → ${_phone.text.trim()}',
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        onConfirm: () => _send(currency),
                      );
                      if (ok && context.mounted) {
                        AppSnack.success(context, 'Transfert effectué.');
                      }
                    }
                  : null,
            ),
          ],
        ),
      ),
    );
  }
}
