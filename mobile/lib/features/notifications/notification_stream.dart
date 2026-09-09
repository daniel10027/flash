import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../auth/auth_controller.dart';
import 'notifications_page.dart';

/// MOB-010 — flux temps réel : se connecte à `GET /v1/notifications/stream`
/// (SSE) tant que l'utilisateur est connecté ; à chaque trame, rafraîchit la
/// liste + le compteur. Repli sur un polling 30 s si le flux tombe.
final unreadCountProvider = StreamProvider<int>((ref) async* {
  if (ref.watch(authControllerProvider).status != AuthStatus.signedIn) {
    yield 0;
    return;
  }
  final api = ref.watch(apiClientProvider);

  Future<int> fetchUnread() async {
    final r = await api.getJson('/v1/notifications');
    return (r['unread'] as num?)?.toInt() ?? 0;
  }

  yield await fetchUnread().catchError((_) => 0);

  while (true) {
    try {
      final res = await api.raw.get<ResponseBody>(
        '/v1/notifications/stream',
        options: Options(
          responseType: ResponseType.stream,
          headers: {'Accept': 'text/event-stream'},
          receiveTimeout: Duration.zero,
        ),
      );
      final lines = res.data!.stream
          .cast<List<int>>()
          .transform(utf8.decoder)
          .transform(const LineSplitter());
      await for (final line in lines) {
        if (line.startsWith('data:')) {
          ref.invalidate(notificationsProvider);
          yield await fetchUnread().catchError((_) => 0);
        }
      }
    } catch (_) {
      // flux coupé : on repasse en polling doux
      await Future<void>.delayed(const Duration(seconds: 30));
      yield await fetchUnread().catchError((_) => 0);
    }
  }
});
