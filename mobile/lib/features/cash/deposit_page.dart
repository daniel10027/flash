import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../../shared/widgets/common.dart';
import '../wallet/wallet_providers.dart';

/// MOB-023 — dépôt cash : mon identifiant / QR à présenter à l'agent.
class DepositPage extends ConsumerWidget {
  const DepositPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final wallet = ref.watch(primaryWalletProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Ajouter de l\'argent')),
      body: wallet.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, __) =>
            const EmptyState(icon: Icons.wifi_off, title: 'Indisponible'),
        data: (w) => w == null
            ? const EmptyState(
                icon: Icons.account_balance_wallet_outlined,
                title: 'Portefeuille indisponible',
              )
            : SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: Column(
                  children: [
                    Text(
                      'Présentez ce code à l\'agent et remettez les espèces : '
                      'votre solde est crédité immédiatement.',
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                    const SizedBox(height: 24),
                    Container(
                      padding: const EdgeInsets.all(20),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: QrImageView(
                        data: 'flash://deposit?w=${w.id}',
                        size: 220,
                      ),
                    ),
                    const SizedBox(height: 16),
                    SelectableText(
                      'Identifiant : ${w.id}',
                      style: TextStyle(color: Theme.of(context).hintColor),
                    ),
                  ],
                ),
              ),
      ),
    );
  }
}
