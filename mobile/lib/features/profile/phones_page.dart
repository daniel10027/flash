import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../../shared/widgets/app_snackbar.dart';
import '../../shared/widgets/common.dart';
import '../../shared/widgets/pin_pad.dart';

final _phonesProvider = FutureProvider.autoDispose((ref) async {
  final r = await ref.watch(apiClientProvider).getJson('/v1/phones');
  return ((r['phone_numbers'] as List?) ?? const [])
      .cast<Map<String, dynamic>>()
      .toList();
});

/// MOB-030 — jusqu'à 5 numéros : ajout (OTP), principal, suppression.
class PhonesPage extends ConsumerWidget {
  const PhonesPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final phones = ref.watch(_phonesProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Mes numéros')),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _addFlow(context, ref),
        icon: const Icon(Icons.add),
        label: const Text('Ajouter'),
      ),
      body: phones.when(
        loading: () => const Padding(
          padding: EdgeInsets.all(16),
          child: Skeleton(height: 64),
        ),
        error: (_, __) => const EmptyState(
          icon: Icons.wifi_off,
          title: 'Chargement impossible',
        ),
        data: (list) => ListView(
          children: [
            for (final p in list)
              ListTile(
                leading: const Icon(Icons.phone_iphone),
                title: Text(p['masked'] as String? ??
                    p['phone_number'] as String? ??
                    '—'),
                subtitle: Text(
                  p['verified'] == true ? 'Vérifié' : 'Non vérifié',
                ),
                trailing: Wrap(
                  spacing: 4,
                  children: [
                    if (p['is_primary'] == true)
                      const Chip(label: Text('Principal'))
                    else ...[
                      TextButton(
                        onPressed: () => _do(
                          context,
                          ref,
                          () => ref.read(apiClientProvider).postJson(
                            '/v1/phones/primary',
                            body: {'phone_number': p['phone_number']},
                          ),
                        ),
                        child: const Text('Principal'),
                      ),
                      IconButton(
                        onPressed: () => _do(
                          context,
                          ref,
                          () => ref.read(apiClientProvider).delete(
                                '/v1/phones?phone_number=${Uri.encodeComponent(p['phone_number'] as String)}',
                              ),
                        ),
                        icon: const Icon(Icons.delete_outline),
                      ),
                    ],
                  ],
                ),
              ),
            const Padding(
              padding: EdgeInsets.all(16),
              child: Text('5 numéros maximum par compte.'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _do(
    BuildContext context,
    WidgetRef ref,
    Future<void> Function() action,
  ) async {
    try {
      await action();
      ref.invalidate(_phonesProvider);
    } catch (e) {
      if (context.mounted) AppSnack.error(context, e);
    }
  }

  void _addFlow(BuildContext context, WidgetRef ref) {
    final phone = TextEditingController();
    final country = TextEditingController(text: 'CI');
    var pendingVerify = false;
    var code = '';

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
              if (!pendingVerify) ...[
                TextField(
                  controller: phone,
                  keyboardType: TextInputType.phone,
                  decoration: const InputDecoration(labelText: 'Numéro'),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: country,
                  maxLength: 2,
                  decoration: const InputDecoration(
                    labelText: 'Pays',
                    counterText: '',
                  ),
                ),
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: () async {
                    try {
                      await ref.read(apiClientProvider).postJson(
                        '/v1/phones',
                        body: {
                          'phone_number': phone.text.trim(),
                          'country': country.text.trim().toUpperCase(),
                        },
                      );
                      setSheet(() => pendingVerify = true);
                    } catch (e) {
                      if (context.mounted) AppSnack.error(context, e);
                    }
                  },
                  child: const Text('Envoyer le code'),
                ),
              ] else ...[
                const Text('Saisissez le code reçu'),
                const SizedBox(height: 16),
                PinPad(
                  length: 6,
                  value: code,
                  onChanged: (v) => setSheet(() => code = v),
                  onCompleted: (v) async {
                    try {
                      await ref.read(apiClientProvider).postJson(
                        '/v1/phones/verify',
                        body: {'phone_number': phone.text.trim(), 'code': v},
                      );
                      ref.invalidate(_phonesProvider);
                      if (context.mounted) Navigator.pop(context);
                      if (context.mounted) {
                        AppSnack.success(context, 'Numéro ajouté.');
                      }
                    } catch (e) {
                      setSheet(() => code = '');
                      if (context.mounted) AppSnack.error(context, e);
                    }
                  },
                ),
              ],
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }
}
