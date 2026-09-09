import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:qr_flutter/qr_flutter.dart';
import 'package:share_plus/share_plus.dart';

import '../../l10n/generated/app_localizations.dart';
import '../../shared/format/money_format.dart';
import '../../shared/widgets/amount_field.dart';
import '../auth/auth_controller.dart';
import '../wallet/wallet_providers.dart';

/// « Mon QR pour recevoir » — encode `flash://pay?u=<id>&amount=<minor>`.
class ReceivePage extends ConsumerStatefulWidget {
  const ReceivePage({super.key});

  @override
  ConsumerState<ReceivePage> createState() => _ReceivePageState();
}

class _ReceivePageState extends ConsumerState<ReceivePage> {
  int _amount = 0;

  @override
  Widget build(BuildContext context) {
    final l = L10n.of(context);
    final userId = ref.watch(authControllerProvider).userId ?? 'me';
    final currency =
        ref.watch(primaryWalletProvider).valueOrNull?.currency ?? 'XOF';
    final payload = _amount > 0
        ? 'flash://pay?u=$userId&amount=$_amount'
        : 'flash://pay?u=$userId';

    return Scaffold(
      appBar: AppBar(
        title: const Text('Recevoir'),
        actions: [
          IconButton(
            onPressed: () => Share.share(payload),
            icon: const Icon(Icons.ios_share),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(20),
              ),
              child: QrImageView(
                data: payload,
                size: 240,
                eyeStyle: const QrEyeStyle(
                  eyeShape: QrEyeShape.circle,
                  color: Colors.black,
                ),
              ),
            ),
            const SizedBox(height: 16),
            Text(
              _amount > 0
                  ? 'Demande de ${formatMoney(_amount, currency)}'
                  : 'Faites scanner ce code pour être payé',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            const SizedBox(height: 24),
            AmountField(
              currency: currency,
              valueMinor: _amount,
              autofocus: false,
              onChanged: (v) => setState(() => _amount = v),
            ),
            const SizedBox(height: 8),
            Text(
              l.comingSoon,
              style:
                  TextStyle(color: Theme.of(context).hintColor, fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }
}
