import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../core/network/api_client.dart';
import '../../l10n/generated/app_localizations.dart';
import '../../shared/format/money_format.dart';
import '../../shared/widgets/amount_field.dart';
import '../../shared/widgets/app_snackbar.dart';
import '../../shared/widgets/confirm_sheet.dart';
import '../../shared/widgets/primary_button.dart';
import '../../shared/widgets/receipt_view.dart';
import '../wallet/wallet_providers.dart';

class _Target {
  const _Target(this.merchantId, this.chargeId);
  final String merchantId;
  final String? chargeId;

  static _Target? parse(String raw) {
    final m = RegExp(r'[?&]m=([^&\s]+)').firstMatch(raw);
    if (m == null) return null;
    final c = RegExp(r'[?&]c=([^&\s]+)').firstMatch(raw);
    return _Target(Uri.decodeComponent(m.group(1)!),
        c == null ? null : Uri.decodeComponent(c.group(1)!));
  }
}

class ScanPage extends ConsumerStatefulWidget {
  const ScanPage({super.key});

  @override
  ConsumerState<ScanPage> createState() => _ScanPageState();
}

class _ScanPageState extends ConsumerState<ScanPage> {
  final _controller = MobileScannerController(
    detectionSpeed: DetectionSpeed.noDuplicates,
  );
  final _manual = TextEditingController();
  _Target? _target;
  int _amount = 0;
  Map<String, dynamic>? _receipt;
  bool _handling = false;

  @override
  void dispose() {
    _controller.dispose();
    _manual.dispose();
    super.dispose();
  }

  void _onDetect(BarcodeCapture cap) {
    if (_target != null || _handling) return;
    final code = cap.barcodes.firstOrNull?.rawValue;
    if (code == null) return;
    final t = _Target.parse(code);
    if (t != null) setState(() => _target = t);
  }

  Future<void> _pay(String currency) async {
    setState(() => _handling = true);
    try {
      final r = await ref.read(apiClientProvider).postJson(
        '/v1/merchant-payments',
        body: {
          'merchant_id': _target!.merchantId,
          if (_target!.chargeId != null) 'charge_id': _target!.chargeId,
          if (_target!.chargeId == null) 'amount_minor': _amount,
        },
      );
      if (mounted) setState(() => _receipt = r);
      refreshDashboard(ref);
    } catch (e) {
      if (mounted) AppSnack.error(context, e);
      rethrow;
    } finally {
      if (mounted) setState(() => _handling = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l = L10n.of(context);
    final currency =
        ref.watch(primaryWalletProvider).valueOrNull?.currency ?? 'XOF';

    if (_receipt != null) {
      return Scaffold(
        appBar: AppBar(title: Text(l.quickPay)),
        body: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            children: [
              ReceiptView(data: _receipt!, title: 'Paiement effectué'),
              const SizedBox(height: 24),
              PrimaryButton(
                label: l.actionBack,
                onPressed: () => setState(() {
                  _receipt = null;
                  _target = null;
                  _amount = 0;
                }),
              ),
            ],
          ),
        ),
      );
    }

    if (_target != null) {
      return Scaffold(
        appBar: AppBar(title: Text(l.quickPay)),
        body: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Marchand : ${_target!.merchantId}',
                  style: Theme.of(context).textTheme.bodyMedium),
              const SizedBox(height: 16),
              if (_target!.chargeId != null)
                const Text('Montant pré-rempli par le marchand.')
              else
                AmountField(
                  currency: currency,
                  valueMinor: _amount,
                  onChanged: (v) => setState(() => _amount = v),
                ),
              const SizedBox(height: 24),
              PrimaryButton(
                label: 'Payer',
                loading: _handling,
                onPressed: _target!.chargeId != null || _amount > 0
                    ? () async {
                        final ok = await showConfirmSheet(
                          context,
                          title: 'Confirmer le paiement',
                          summary: Text(
                            _target!.chargeId != null
                                ? 'Marchand ${_target!.merchantId}'
                                : '${formatMoney(_amount, currency)} · ${_target!.merchantId}',
                          ),
                          onConfirm: () => _pay(currency),
                        );
                        if (ok && context.mounted) {
                          AppSnack.success(context, 'Paiement effectué.');
                        }
                      }
                    : null,
              ),
              TextButton(
                onPressed: () => setState(() => _target = null),
                child: const Text('Scanner un autre code'),
              ),
            ],
          ),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(title: Text(l.navScan)),
      body: Column(
        children: [
          Expanded(
            child: Stack(
              alignment: Alignment.center,
              children: [
                MobileScanner(controller: _controller, onDetect: _onDetect),
                // Cadre de visée.
                Container(
                  width: 220,
                  height: 220,
                  decoration: BoxDecoration(
                    border: Border.all(color: Colors.white, width: 3),
                    borderRadius: BorderRadius.circular(20),
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _manual,
                    decoration: const InputDecoration(
                      labelText: 'Code marchand',
                      hintText: 'flash://pay?m=…',
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                FilledButton(
                  onPressed: () {
                    final t = _Target.parse(_manual.text);
                    if (t == null) {
                      AppSnack.error(context, 'Code invalide.');
                    } else {
                      setState(() => _target = t);
                    }
                  },
                  child: const Text('OK'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
