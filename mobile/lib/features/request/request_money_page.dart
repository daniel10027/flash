import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/network/api_client.dart';
import '../../shared/widgets/amount_field.dart';
import '../../shared/widgets/app_snackbar.dart';
import '../../shared/widgets/common.dart';
import '../../shared/widgets/money_text.dart';
import '../wallet/wallet_providers.dart';

final _requestsProvider =
    FutureProvider.autoDispose.family<List<Map<String, dynamic>>, String>(
  (ref, direction) async {
    final r = await ref
        .watch(apiClientProvider)
        .getJson('/v1/payment-requests', query: {'direction': direction});
    return ((r['requests'] as List?) ?? const [])
        .cast<Map<String, dynamic>>()
        .toList();
  },
);

/// MOB-019 — demander de l'argent : créer, partager, listes reçues / émises.
class RequestMoneyPage extends ConsumerWidget {
  const RequestMoneyPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Demandes'),
          bottom: const TabBar(
            tabs: [Tab(text: 'Reçues'), Tab(text: 'Émises')],
          ),
        ),
        floatingActionButton: FloatingActionButton.extended(
          onPressed: () => _create(context, ref),
          icon: const Icon(Icons.add),
          label: const Text('Demander'),
        ),
        body: const TabBarView(
          children: [
            _RequestList(direction: 'incoming'),
            _RequestList(direction: 'outgoing'),
          ],
        ),
      ),
    );
  }

  void _create(BuildContext context, WidgetRef ref) {
    final phone = TextEditingController();
    final note = TextEditingController();
    var amount = 0;
    final currency =
        ref.read(primaryWalletProvider).valueOrNull?.currency ?? 'XOF';

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
                    const InputDecoration(labelText: 'Numéro du payeur'),
              ),
              const SizedBox(height: 12),
              AmountField(
                currency: currency,
                valueMinor: amount,
                autofocus: false,
                onChanged: (v) => setSheet(() => amount = v),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: note,
                decoration: const InputDecoration(labelText: 'Motif (option)'),
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: amount > 0 && phone.text.trim().isNotEmpty
                    ? () async {
                        try {
                          final r = await ref.read(apiClientProvider).postJson(
                            '/v1/payment-requests',
                            body: {
                              'payer_phone_number': phone.text.trim(),
                              'amount_minor': amount,
                              if (note.text.trim().isNotEmpty)
                                'note': note.text.trim(),
                            },
                          );
                          ref.invalidate(_requestsProvider);
                          if (context.mounted) Navigator.pop(context);
                          final link = r['share_url'] ??
                              'flash://request?id=${r['request_id'] ?? r['id']}';
                          await Share.share(
                              'Demande de paiement Flash : $link');
                        } catch (e) {
                          if (context.mounted) AppSnack.error(context, e);
                        }
                      }
                    : null,
                child: const Text('Créer et partager'),
              ),
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }
}

class _RequestList extends ConsumerWidget {
  const _RequestList({required this.direction});
  final String direction;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final list = ref.watch(_requestsProvider(direction));
    return list.when(
      loading: () => const Padding(
        padding: EdgeInsets.all(16),
        child: Skeleton(height: 64),
      ),
      error: (_, __) =>
          const EmptyState(icon: Icons.wifi_off, title: 'Indisponible'),
      data: (items) => items.isEmpty
          ? const EmptyState(
              icon: Icons.request_quote_outlined,
              title: 'Aucune demande',
            )
          : RefreshIndicator(
              onRefresh: () async =>
                  ref.invalidate(_requestsProvider(direction)),
              child: ListView.separated(
                itemCount: items.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (context, i) {
                  final r = items[i];
                  final status = r['status'] as String? ?? 'PENDING';
                  final id = r['request_id'] ?? r['id'];
                  return ListTile(
                    title: MoneyText(
                      (r['amount_minor'] as num?)?.toInt() ?? 0,
                      r['currency'] as String? ?? 'XOF',
                    ),
                    subtitle: Text('${r['note'] ?? ''} · $status'),
                    trailing: (direction == 'incoming' && status == 'PENDING')
                        ? Wrap(
                            children: [
                              TextButton(
                                onPressed: () =>
                                    _act(context, ref, id, 'accept'),
                                child: const Text('Payer'),
                              ),
                              TextButton(
                                onPressed: () =>
                                    _act(context, ref, id, 'decline'),
                                child: const Text('Refuser'),
                              ),
                            ],
                          )
                        : (status == 'PENDING'
                            ? TextButton(
                                onPressed: () =>
                                    _act(context, ref, id, 'cancel'),
                                child: const Text('Annuler'),
                              )
                            : null),
                  );
                },
              ),
            ),
    );
  }

  Future<void> _act(
    BuildContext context,
    WidgetRef ref,
    Object? id,
    String op,
  ) async {
    try {
      await ref
          .read(apiClientProvider)
          .postJson('/v1/payment-requests/$id/$op');
      ref
        ..invalidate(_requestsProvider('incoming'))
        ..invalidate(_requestsProvider('outgoing'));
    } catch (e) {
      if (context.mounted) AppSnack.error(context, e);
    }
  }
}
