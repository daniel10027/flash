import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../../shared/format/money_format.dart';
import '../../shared/widgets/amount_field.dart';
import '../../shared/widgets/app_snackbar.dart';
import '../../shared/widgets/common.dart';
import '../../shared/widgets/primary_button.dart';

final agentProfileProvider = FutureProvider.autoDispose((ref) async {
  return ref.watch(apiClientProvider).getJson('/v1/agent');
});

/// Vrai si le compte courant a un espace agent (affiche l'entrée dans le profil).
final isAgentProvider = FutureProvider.autoDispose<bool>((ref) async {
  try {
    await ref.watch(apiClientProvider).getJson('/v1/agent');
    return true;
  } catch (_) {
    return false;
  }
});

/// MOB-036 — mode agent léger : float, commissions, dépôt client, confirmation
/// de retrait.
class AgentPage extends ConsumerWidget {
  const AgentPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final agent = ref.watch(agentProfileProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Espace agent')),
      body: agent.when(
        loading: () => const Padding(
          padding: EdgeInsets.all(16),
          child: Skeleton(height: 120),
        ),
        error: (_, __) =>
            const EmptyState(icon: Icons.badge_outlined, title: 'Non agent'),
        data: (a) {
          final cur = a['currency'] as String? ?? 'XOF';
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Float disponible',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                      Text(
                        formatMoney(
                          (a['float_available_minor'] as num?)?.toInt() ?? 0,
                          cur,
                        ),
                        style: Theme.of(context).textTheme.headlineSmall,
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Commissions dues : ${formatMoney((a['commission_owed_minor'] as num?)?.toInt() ?? 0, cur)}',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(height: 16),
              PrimaryButton(
                label: 'Dépôt client',
                icon: Icons.south_west,
                onPressed: () => _deposit(context, ref, cur),
              ),
              const SizedBox(height: 10),
              OutlinedButton.icon(
                onPressed: () => _confirmWithdrawal(context, ref),
                icon: const Icon(Icons.north_east),
                label: const Text('Confirmer un retrait client'),
              ),
            ],
          );
        },
      ),
    );
  }

  void _deposit(BuildContext context, WidgetRef ref, String currency) {
    final phone = TextEditingController();
    var amount = 0;
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => StatefulBuilder(
        builder: (context, setSheet) => Padding(
          padding: EdgeInsets.only(
            left: 20,
            right: 20,
            bottom: MediaQuery.viewInsetsOf(context).bottom + 20,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: phone,
                keyboardType: TextInputType.phone,
                decoration:
                    const InputDecoration(labelText: 'Numéro du client'),
              ),
              const SizedBox(height: 12),
              AmountField(
                currency: currency,
                valueMinor: amount,
                autofocus: false,
                onChanged: (v) => setSheet(() => amount = v),
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: amount > 0 && phone.text.trim().isNotEmpty
                    ? () async {
                        try {
                          await ref.read(apiClientProvider).postJson(
                            '/v1/agent/deposits',
                            body: {
                              'client_phone_number': phone.text.trim(),
                              'amount_minor': amount,
                            },
                          );
                          ref.invalidate(agentProfileProvider);
                          if (context.mounted) Navigator.pop(context);
                          if (context.mounted) {
                            AppSnack.success(context, 'Dépôt effectué.');
                          }
                        } catch (e) {
                          if (context.mounted) AppSnack.error(context, e);
                        }
                      }
                    : null,
                child: const Text('Encaisser et créditer'),
              ),
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }

  void _confirmWithdrawal(BuildContext context, WidgetRef ref) {
    final code = TextEditingController();
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Code de retrait'),
        content: TextField(
          controller: code,
          autofocus: true,
          decoration:
              const InputDecoration(hintText: 'Code présenté par le client'),
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
                  '/v1/agent/withdrawals/confirm',
                  body: {'code': code.text.trim()},
                );
                ref.invalidate(agentProfileProvider);
                if (context.mounted) {
                  AppSnack.success(context, 'Retrait confirmé.');
                }
              } catch (e) {
                if (context.mounted) AppSnack.error(context, e);
              }
            },
            child: const Text('Confirmer'),
          ),
        ],
      ),
    );
  }
}
