import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../../shared/format/money_format.dart';
import '../../shared/widgets/amount_field.dart';
import '../../shared/widgets/app_snackbar.dart';
import '../../shared/widgets/primary_button.dart';
import '../wallet/wallet_providers.dart';

/// MOB-022 — retrait cash : génère un code, compte à rebours, annulation.
class WithdrawPage extends ConsumerStatefulWidget {
  const WithdrawPage({super.key});

  @override
  ConsumerState<WithdrawPage> createState() => _WithdrawPageState();
}

class _WithdrawPageState extends ConsumerState<WithdrawPage> {
  int _amount = 0;
  Map<String, dynamic>? _order;
  Timer? _timer;
  Duration _left = Duration.zero;
  bool _busy = false;

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _startCountdown(String expiresAt) {
    final end = DateTime.parse(expiresAt);
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      final d = end.difference(DateTime.now());
      setState(() => _left = d.isNegative ? Duration.zero : d);
      if (d.isNegative) _timer?.cancel();
    });
  }

  Future<void> _generate() async {
    setState(() => _busy = true);
    try {
      final r = await ref
          .read(apiClientProvider)
          .postJson('/v1/withdrawals', body: {'amount_minor': _amount});
      setState(() => _order = r);
      _startCountdown(r['expires_at'] as String);
      refreshDashboard(ref);
    } catch (e) {
      if (mounted) AppSnack.error(context, e);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _cancel() async {
    try {
      await ref
          .read(apiClientProvider)
          .postJson('/v1/withdrawals/${_order!['order_id']}/cancel');
      _timer?.cancel();
      setState(() => _order = null);
      refreshDashboard(ref);
    } catch (e) {
      if (mounted) AppSnack.error(context, e);
    }
  }

  @override
  Widget build(BuildContext context) {
    final currency =
        ref.watch(primaryWalletProvider).valueOrNull?.currency ?? 'XOF';

    if (_order != null) {
      final code = _order!['code'] as String? ?? '——————';
      final m = _left.inMinutes;
      final s = _left.inSeconds % 60;
      return Scaffold(
        appBar: AppBar(title: const Text('Code de retrait')),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  'Montrez ce code à l\'agent',
                  style: TextStyle(color: Theme.of(context).hintColor),
                ),
                const SizedBox(height: 16),
                Text(
                  code,
                  style: Theme.of(context).textTheme.displayMedium?.copyWith(
                        fontWeight: FontWeight.w800,
                        letterSpacing: 8,
                      ),
                ).animate().scale(
                      begin: const Offset(0.8, 0.8),
                      curve: Curves.easeOutBack,
                    ),
                const SizedBox(height: 12),
                Text(
                  '${formatMoney((_order!['amount_minor'] as num).toInt(), currency)}'
                  ' · frais ${formatMoney((_order!['fee_minor'] as num?)?.toInt() ?? 0, currency)}',
                ),
                const SizedBox(height: 8),
                Text(
                  _left == Duration.zero
                      ? 'Expiré'
                      : 'Expire dans $m:${s.toString().padLeft(2, '0')}',
                  style:
                      TextStyle(color: Theme.of(context).colorScheme.primary),
                ),
                const SizedBox(height: 24),
                TextButton.icon(
                  onPressed: _cancel,
                  icon: const Icon(Icons.close),
                  label: const Text('Annuler le code'),
                ),
              ],
            ),
          ),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Retirer de l\'argent')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            Text(
              'Générez un code à présenter chez un agent Flash.',
              style: Theme.of(context).textTheme.bodyMedium,
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
              label: 'Générer le code',
              loading: _busy,
              onPressed: _amount > 0 ? _generate : null,
            ),
          ],
        ),
      ),
    );
  }
}
