import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../../core/network/api_client.dart';
import '../../shared/widgets/common.dart';

final notificationsProvider = FutureProvider.autoDispose((ref) async {
  final r = await ref.watch(apiClientProvider).getJson('/v1/notifications');
  return (
    items: ((r['notifications'] as List?) ?? const [])
        .cast<Map<String, dynamic>>()
        .toList(),
    unread: (r['unread'] as num?)?.toInt() ?? 0,
  );
});

/// MOB-032 — centre de notifications : liste + marquage lu.
class NotificationsPage extends ConsumerWidget {
  const NotificationsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(notificationsProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Notifications'),
        actions: [
          TextButton(
            onPressed: () async {
              try {
                await ref
                    .read(apiClientProvider)
                    .postJson('/v1/notifications/read-all');
                ref.invalidate(notificationsProvider);
              } catch (_) {}
            },
            child: const Text('Tout lire'),
          ),
        ],
      ),
      body: async.when(
        loading: () => ListView(
          padding: const EdgeInsets.all(16),
          children: List.generate(
            6,
            (_) => const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Skeleton(height: 48),
            ),
          ),
        ),
        error: (_, __) => const EmptyState(
          icon: Icons.wifi_off,
          title: 'Chargement impossible',
        ),
        data: (data) => data.items.isEmpty
            ? const EmptyState(
                icon: Icons.notifications_off_outlined,
                title: 'Aucune notification',
              )
            : RefreshIndicator(
                onRefresh: () async => ref.invalidate(notificationsProvider),
                child: ListView.separated(
                  itemCount: data.items.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, i) {
                    final n = data.items[i];
                    final read = n['read'] == true;
                    return ListTile(
                      leading: Icon(
                        read
                            ? Icons.notifications_none
                            : Icons.notifications_active,
                        color: read
                            ? Theme.of(context).hintColor
                            : Theme.of(context).colorScheme.primary,
                      ),
                      title: Text(n['title'] as String? ?? '—'),
                      subtitle: Text(n['body'] as String? ?? ''),
                      trailing: n['created_at'] != null
                          ? Text(
                              DateFormat.MMMd('fr').format(
                                DateTime.parse(n['created_at'] as String),
                              ),
                              style: Theme.of(context).textTheme.labelSmall,
                            )
                          : null,
                      onTap: read
                          ? null
                          : () async {
                              try {
                                await ref.read(apiClientProvider).postJson(
                                      '/v1/notifications/${n['id']}/read',
                                    );
                                ref.invalidate(notificationsProvider);
                              } catch (_) {}
                            },
                    );
                  },
                ),
              ),
      ),
    );
  }
}
