import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../../shared/widgets/amount_sheet.dart';
import '../../shared/widgets/app_snackbar.dart';
import '../../shared/widgets/common.dart';
import '../../shared/widgets/money_text.dart';
import '../wallet/wallet_providers.dart';

final _vaultProvider = FutureProvider.autoDispose((ref) async {
  final r = await ref.watch(apiClientProvider).getJson('/v1/vault');
  return ((r['pockets'] as List?) ?? const [])
      .cast<Map<String, dynamic>>()
      .toList();
});

/// MOB-027 — coffre : poches, alimenter / retirer, poche verrouillée.
class VaultPage extends ConsumerWidget {
  const VaultPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final pockets = ref.watch(_vaultProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Coffre')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _createPocket(context, ref),
        icon: const Icon(Icons.add),
        label: const Text('Nouvelle poche'),
      ),
      body: pockets.when(
        loading: () => const Padding(
          padding: EdgeInsets.all(16),
          child: Skeleton(height: 80),
        ),
        error: (_, __) =>
            const EmptyState(icon: Icons.wifi_off, title: 'Indisponible'),
        data: (list) => list.isEmpty
            ? const EmptyState(
                icon: Icons.savings_outlined,
                title: 'Aucune poche',
                message: 'Mettez de l\'argent de côté par objectif.',
              )
            : ListView(
                padding: const EdgeInsets.all(16),
                children: [for (final p in list) _PocketCard(pocket: p)],
              ),
      ),
    );
  }

  void _createPocket(BuildContext context, WidgetRef ref) {
    final name = TextEditingController();
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Nouvelle poche'),
        content: TextField(
          controller: name,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Nom'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Annuler'),
          ),
          FilledButton(
            onPressed: () async {
              Navigator.pop(context);
              try {
                await ref.read(apiClientProvider).postJson(
                  '/v1/vault/pockets',
                  body: {'name': name.text.trim()},
                );
                ref.invalidate(_vaultProvider);
              } catch (e) {
                if (context.mounted) AppSnack.error(context, e);
              }
            },
            child: const Text('Créer'),
          ),
        ],
      ),
    );
  }
}

class _PocketCard extends ConsumerWidget {
  const _PocketCard({required this.pocket});
  final Map<String, dynamic> pocket;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final currency = pocket['currency'] as String? ?? 'XOF';
    final locked = pocket['locked'] == true;
    final id = pocket['id'];

    Future<void> move(String op, String title) async {
      final amount =
          await promptAmount(context, currency: currency, title: title);
      if (amount == null) return;
      try {
        await ref.read(apiClientProvider).postJson(
          '/v1/vault/pockets/$id/$op',
          body: {'amount_minor': amount},
        );
        ref
          ..invalidate(_vaultProvider)
          ..invalidate(primaryWalletProvider);
      } catch (e) {
        if (context.mounted) AppSnack.error(context, e);
      }
    }

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(
                  pocket['name'] as String? ?? 'Poche',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const Spacer(),
                if (locked) const Icon(Icons.lock, size: 18),
              ],
            ),
            const SizedBox(height: 4),
            MoneyText(
              (pocket['balance_minor'] as num?)?.toInt() ?? 0,
              currency,
              style: Theme.of(context).textTheme.headlineSmall,
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                TextButton(
                  onPressed: locked ? null : () => move('deposit', 'Alimenter'),
                  child: const Text('Alimenter'),
                ),
                TextButton(
                  onPressed: locked ? null : () => move('withdraw', 'Retirer'),
                  child: const Text('Retirer'),
                ),
                const Spacer(),
                IconButton(
                  onPressed: () async {
                    try {
                      await ref.read(apiClientProvider).postJson(
                            '/v1/vault/pockets/$id/${locked ? 'unlock' : 'lock'}',
                          );
                      ref.invalidate(_vaultProvider);
                    } catch (e) {
                      if (context.mounted) AppSnack.error(context, e);
                    }
                  },
                  icon: Icon(locked ? Icons.lock_open : Icons.lock_outline),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
