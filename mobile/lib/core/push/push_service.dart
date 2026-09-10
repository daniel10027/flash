import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../network/api_client.dart';

/// MOB-009 — notifications push (FCM, gratuit).
///
/// L'initialisation est **tolérante** : sans `google-services.json` /
/// `GoogleService-Info.plist` (générés par `flutterfire configure`), Firebase
/// n'est pas disponible et le push reste simplement inactif — l'app fonctionne.
///
/// `onForegroundMessage` émet à chaque message reçu au premier plan ; la couche
/// applicative s'y abonne pour rafraîchir le centre de notifications.
class PushService {
  PushService(this._ref);
  final Ref _ref;

  final _foreground = StreamController<void>.broadcast();
  Stream<void> get onForegroundMessage => _foreground.stream;

  Future<void> init() async {
    try {
      await Firebase.initializeApp();
      final messaging = FirebaseMessaging.instance;

      final settings = await messaging.requestPermission();
      if (settings.authorizationStatus == AuthorizationStatus.denied) return;

      final token = await messaging.getToken();
      if (token != null) await _register(token);
      messaging.onTokenRefresh.listen(_register);

      FirebaseMessaging.onMessage.listen((_) => _foreground.add(null));
    } catch (e) {
      if (kDebugMode) {
        debugPrint('[push] Firebase indisponible, push désactivé : $e');
      }
    }
  }

  Future<void> _register(String token) async {
    try {
      await _ref
          .read(apiClientProvider)
          .postJson('/v1/notifications/devices', body: {'fcm_token': token});
    } catch (_) {
      // endpoint d'enregistrement pas encore exposé par l'API — sans conséquence
    }
  }

  void dispose() => _foreground.close();
}

final pushServiceProvider = Provider<PushService>((ref) {
  final s = PushService(ref);
  ref.onDispose(s.dispose);
  return s;
});
