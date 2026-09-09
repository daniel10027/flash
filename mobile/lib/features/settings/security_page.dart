import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/network/api_client.dart';
import '../../shared/widgets/app_snackbar.dart';
import '../../shared/widgets/common.dart';
import '../../shared/widgets/pin_pad.dart';
import '../../shared/widgets/primary_button.dart';
import '../auth/auth_controller.dart';

final _devicesProvider = FutureProvider.autoDispose((ref) async {
  final r = await ref.watch(apiClientProvider).getJson('/v1/auth/devices');
  return ((r['devices'] as List?) ?? const [])
      .cast<Map<String, dynamic>>()
      .toList();
});

/// MOB-033 — sécurité : appareils connectés, déconnexion à distance, code secret.
class SecurityPage extends ConsumerWidget {
  const SecurityPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final devices = ref.watch(_devicesProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Sécurité')),
      body: ListView(
        children: [
          ListTile(
            leading: const Icon(Icons.password_outlined),
            title: const Text('Changer le code secret'),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => _changePin(context, ref),
          ),
          const Divider(),
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: Text('Appareils connectés'),
          ),
          devices.when(
            loading: () => const Padding(
              padding: EdgeInsets.all(16),
              child: Skeleton(height: 56),
            ),
            error: (_, __) => const Padding(
              padding: EdgeInsets.all(16),
              child: Text('Impossible de charger les appareils.'),
            ),
            data: (list) => Column(
              children: [
                for (final d in list)
                  ListTile(
                    leading: Icon(
                      d['current'] == true
                          ? Icons.smartphone
                          : Icons.devices_other,
                    ),
                    title: Text(
                      d['current'] == true
                          ? 'Cet appareil'
                          : 'Appareil ${(d['device_id'] as String? ?? '').characters.take(8)}',
                    ),
                    subtitle: d['last_seen'] != null
                        ? Text(
                            'Vu ${DateFormat.yMMMd('fr').add_Hm().format(DateTime.parse(d['last_seen'] as String))}',
                          )
                        : null,
                    trailing: d['current'] == true
                        ? const Chip(label: Text('actuel'))
                        : TextButton(
                            onPressed: () async {
                              try {
                                await ref.read(apiClientProvider).delete(
                                    '/v1/auth/devices/${d['device_id']}');
                                ref.invalidate(_devicesProvider);
                                if (context.mounted) {
                                  AppSnack.success(
                                    context,
                                    'Appareil déconnecté.',
                                  );
                                }
                              } catch (e) {
                                if (context.mounted) {
                                  AppSnack.error(context, e);
                                }
                              }
                            },
                            child: const Text('Déconnecter'),
                          ),
                  ),
              ],
            ),
          ),
          const Divider(),
          Padding(
            padding: const EdgeInsets.all(16),
            child: OutlinedButton.icon(
              onPressed: () =>
                  ref.read(authControllerProvider.notifier).signOut(),
              icon: const Icon(Icons.logout),
              label: const Text('Se déconnecter de cet appareil'),
            ),
          ),
        ],
      ),
    );
  }

  void _changePin(BuildContext context, WidgetRef ref) {
    var current = '';
    var next = '';
    var step = 0;
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
              Text(step == 0 ? 'Code actuel' : 'Nouveau code'),
              const SizedBox(height: 20),
              PinPad(
                length: 4,
                value: step == 0 ? current : next,
                onChanged: (v) =>
                    setSheet(() => step == 0 ? current = v : next = v),
                onCompleted: (v) async {
                  if (step == 0) {
                    setSheet(() => step = 1);
                    return;
                  }
                  try {
                    await ref.read(apiClientProvider).postJson(
                      '/v1/auth/change-pin',
                      body: {'current_pin': current, 'new_pin': v},
                    );
                    if (context.mounted) Navigator.pop(context);
                    if (context.mounted) {
                      AppSnack.success(context, 'Code secret modifié.');
                    }
                  } catch (e) {
                    setSheet(() {
                      step = 0;
                      current = '';
                      next = '';
                    });
                    if (context.mounted) AppSnack.error(context, e);
                  }
                },
              ),
              const SizedBox(height: 12),
              const PrimaryButton(label: 'Saisissez le code', onPressed: null),
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }
}
