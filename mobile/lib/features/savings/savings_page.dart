import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../../shared/format/money_format.dart';
import '../../shared/widgets/amount_sheet.dart';
import '../../shared/widgets/app_snackbar.dart';
import '../../shared/widgets/common.dart';
import '../../shared/widgets/money_text.dart';
import '../wallet/wallet_providers.dart';

final _plansProvider = FutureProvider.autoDispose((ref) async {
  final r = await ref.watch(apiClientProvider).getJson('/v1/savings/plans');
  return ((r['plans'] as List?) ?? const [])
      .cast<Map<String, dynamic>>()
      .toList();
});

/// MOB-028 — épargne : plans, progression, versement manuel, clôture.
class SavingsPage extends ConsumerWidget {
  const SavingsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final plans = ref.watch(_plansProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Épargne')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _open(context, ref),
        icon: const Icon(Icons.add),
        label: const Text('Nouveau plan'),
      ),
      body: plans.when(
        loading: () => const Padding(
          padding: EdgeInsets.all(16),
          child: Skeleton(height: 96),
        ),
        error: (_, __) =>
            const EmptyState(icon: Icons.wifi_off, title: 'Indisponible'),
        data: (list) => list.isEmpty
            ? const EmptyState(
                icon: Icons.trending_up,
                title: 'Aucun plan',
                message:
                    'Fixez un objectif et laissez vos intérêts travailler.',
              )
            : ListView(
                padding: const EdgeInsets.all(16),
                children: [for (final p in list) _PlanCard(plan: p)],
              ),
      ),
    );
  }

  void _open(BuildContext context, WidgetRef ref) async {
    final currency =
        ref.read(primaryWalletProvider).valueOrNull?.currency ?? 'XOF';
    final goal =
        await promptAmount(context, currency: currency, title: 'Objectif');
    if (goal == null) return;
    try {
      await ref.read(apiClientProvider).postJson(
        '/v1/savings/plans',
        body: {'goal_minor': goal, 'annual_rate_bps': 400},
      );
      ref.invalidate(_plansProvider);
    } catch (e) {
      if (context.mounted) AppSnack.error(context, e);
    }
  }
}

class _PlanCard extends ConsumerWidget {
  const _PlanCard({required this.plan});
  final Map<String, dynamic> plan;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final currency = plan['currency'] as String? ?? 'XOF';
    final saved = (plan['saved_minor'] as num?)?.toInt() ?? 0;
    final goal = (plan['goal_minor'] as num?)?.toInt() ?? 0;
    final ratio = goal > 0 ? (saved / goal).clamp(0.0, 1.0) : 0.0;
    final rate = ((plan['annual_rate_bps'] as num?)?.toInt() ?? 0) / 100;
    final id = plan['id'];

    Future<void> act(String op, String title) async {
      final amount =
          await promptAmount(context, currency: currency, title: title);
      if (amount == null) return;
      try {
        await ref.read(apiClientProvider).postJson(
          '/v1/savings/plans/$id/$op',
          body: {'amount_minor': amount},
        );
        ref
          ..invalidate(_plansProvider)
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
                MoneyText(
                  saved,
                  currency,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
                const Spacer(),
                Chip(label: Text('${rate.toStringAsFixed(1)} %/an')),
              ],
            ),
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: LinearProgressIndicator(
                value: ratio,
                minHeight: 8,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              'Objectif ${formatMoney(goal, currency)} · ${(ratio * 100).round()} %',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                TextButton(
                  onPressed: () => act('deposit', 'Verser'),
                  child: const Text('Verser'),
                ),
                TextButton(
                  onPressed: () => act('withdraw', 'Retirer'),
                  child: const Text('Retirer'),
                ),
                const Spacer(),
                TextButton(
                  onPressed: () async {
                    try {
                      await ref
                          .read(apiClientProvider)
                          .postJson('/v1/savings/plans/$id/close');
                      ref
                        ..invalidate(_plansProvider)
                        ..invalidate(primaryWalletProvider);
                    } catch (e) {
                      if (context.mounted) AppSnack.error(context, e);
                    }
                  },
                  child: const Text('Clôturer'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
