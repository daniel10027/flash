import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../../core/storage/secure_store.dart';

enum AuthStatus { unknown, signedOut, locked, signedIn }

@immutable
class AuthState {
  const AuthState({required this.status, this.userId});
  final AuthStatus status;
  final String? userId;

  AuthState copyWith({AuthStatus? status, String? userId}) =>
      AuthState(status: status ?? this.status, userId: userId ?? this.userId);
}

/// Machine à états d'authentification :
///  * `unknown`   : au démarrage, avant lecture du stockage sécurisé ;
///  * `signedOut` : aucune session ;
///  * `locked`    : un refresh token existe mais l'app doit être déverrouillée
///                  par PIN / biométrie (MOB-005, MOB-011) ;
///  * `signedIn`  : jeton d'accès en mémoire, navigation libre.
class AuthController extends StateNotifier<AuthState> {
  AuthController(this._store, this._api)
      : super(const AuthState(status: AuthStatus.unknown));

  final SecureStore _store;
  final ApiClient _api;

  Future<void> bootstrap() async {
    final refresh = await _store.readRefreshToken();
    state = AuthState(
      status: refresh == null ? AuthStatus.signedOut : AuthStatus.locked,
    );
  }

  /// Appelé après une connexion / inscription réussie.
  Future<void> onSession({
    required String accessToken,
    required String refreshToken,
    String? userId,
  }) async {
    await _store.writeRefreshToken(refreshToken);
    _api.accessToken = accessToken;
    state = AuthState(status: AuthStatus.signedIn, userId: userId);
  }

  /// Déverrouillage réussi (PIN correct / biométrie OK) : on tente un refresh
  /// pour récupérer un jeton d'accès frais.
  Future<bool> unlock() async {
    final refresh = await _store.readRefreshToken();
    if (refresh == null) {
      state = const AuthState(status: AuthStatus.signedOut);
      return false;
    }
    try {
      final r = await _api.postJson(
        '/v1/auth/refresh',
        body: {'refresh_token': refresh},
      );
      _api.accessToken = r['access_token'] as String?;
      final newRefresh = r['refresh_token'] as String?;
      if (newRefresh != null) await _store.writeRefreshToken(newRefresh);
      state = const AuthState(status: AuthStatus.signedIn);
      return true;
    } catch (_) {
      // refresh révoqué -> retour à la connexion
      await _store.clearRefreshToken();
      state = const AuthState(status: AuthStatus.signedOut);
      return false;
    }
  }

  void lock() => state = const AuthState(status: AuthStatus.locked);

  Future<void> signOut() async {
    await _store.clearRefreshToken();
    _api.accessToken = null;
    state = const AuthState(status: AuthStatus.signedOut);
  }
}

final authControllerProvider =
    StateNotifierProvider<AuthController, AuthState>((ref) {
  return AuthController(
    ref.watch(secureStoreProvider),
    ref.watch(apiClientProvider),
  );
});
