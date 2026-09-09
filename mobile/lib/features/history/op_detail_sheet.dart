import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:share_plus/share_plus.dart';

import '../../core/network/api_client.dart';
import '../../shared/widgets/common.dart';
import '../../shared/widgets/receipt_view.dart';

/// MOB-026 / MOB-035 — détail d'une opération + reçu partageable.
void showOpDetail(BuildContext context, String reference) {
  showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (context) => _OpDetailBody(reference: reference),
  );
}

class _OpDetailBody extends ConsumerWidget {
  const _OpDetailBody({required this.reference});
  final String reference;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final receipt = ref.watch(_receiptProvider(reference));
    return Padding(
      padding: EdgeInsets.only(
        left: 20,
        right: 20,
        top: 4,
        bottom: MediaQuery.paddingOf(context).bottom + 20,
      ),
      child: receipt.when(
        loading: () => const Padding(
          padding: EdgeInsets.all(32),
          child: Center(child: CircularProgressIndicator()),
        ),
        error: (_, __) => const EmptyState(
          icon: Icons.receipt_long,
          title: 'Reçu indisponible',
        ),
        data: (data) => SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ReceiptView(data: data, title: 'Reçu'),
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: () => Share.share(
                  data.entries
                      .where((e) => e.value is! Map && e.value is! List)
                      .map((e) => '${e.key.replaceAll('_', ' ')}: ${e.value}')
                      .join('\n'),
                  subject: 'Reçu Flash $reference',
                ),
                icon: const Icon(Icons.ios_share),
                label: const Text('Partager le reçu'),
              ),
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }
}

final _receiptProvider = FutureProvider.autoDispose
    .family<Map<String, dynamic>, String>((ref, reference) async {
  return ref.watch(apiClientProvider).getJson('/v1/receipts/$reference');
});
