import 'package:dio/dio.dart';
import 'package:flash_app/core/network/api_client.dart';

/// Faux client HTTP pour les tests : renvoie des réponses cannées par préfixe
/// de chemin. `route('/v1/wallets', {...})` enregistre une réponse.
class FakeApiClient implements ApiClient {
  final Map<String, Map<String, dynamic>> _responses = {};
  final List<String> calls = [];

  void route(String path, Map<String, dynamic> body) => _responses[path] = body;

  Map<String, dynamic> _match(String path) {
    calls.add(path);
    for (final entry in _responses.entries) {
      if (path.startsWith(entry.key)) return entry.value;
    }
    return const {};
  }

  @override
  Future<Map<String, dynamic>> getJson(String path,
          {Map<String, dynamic>? query}) async =>
      _match(path);

  @override
  Future<Map<String, dynamic>> postJson(String path,
          {Object? body, String? idempotencyKey}) async =>
      _match(path);

  @override
  Future<void> delete(String path) async => _match(path);

  @override
  set accessToken(String? value) {}

  @override
  Dio get raw => throw UnimplementedError();
}
