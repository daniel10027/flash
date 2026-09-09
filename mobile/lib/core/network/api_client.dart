import 'dart:math';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../env/flavor.dart';
import '../storage/secure_store.dart';
import 'api_exception.dart';

/// Client HTTP unique de l'app. Interceptors :
///  * `X-Request-ID` sur chaque requête ;
///  * `Idempotency-Key` auto sur les écritures ;
///  * jeton d'accès en mémoire + rafraîchissement transparent sur 401 (une fois) ;
///  * conversion des erreurs Dio en [ApiException] / [NetworkException].
class ApiClient {
  ApiClient(this._store) {
    _dio = Dio(
      BaseOptions(
        baseUrl: Env.apiBaseUrl,
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 20),
        headers: {'Accept': 'application/json'},
      ),
    );
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: _onRequest,
        onError: _onError,
      ),
    );
  }

  final SecureStore _store;
  late final Dio _dio;

  String? _accessToken;
  bool _refreshing = false;

  Dio get raw => _dio;
  set accessToken(String? value) => _accessToken = value;

  final _rng = Random.secure();
  String _uuid() {
    final b = List<int>.generate(16, (_) => _rng.nextInt(256));
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    final h = b.map((x) => x.toRadixString(16).padLeft(2, '0')).join();
    return '${h.substring(0, 8)}-${h.substring(8, 12)}-${h.substring(12, 16)}'
        '-${h.substring(16, 20)}-${h.substring(20)}';
  }

  void _onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    options.headers['X-Request-ID'] = _uuid();
    final method = options.method.toUpperCase();
    if (method != 'GET' && !options.headers.containsKey('Idempotency-Key')) {
      options.headers['Idempotency-Key'] = _uuid();
    }
    if (_accessToken != null && options.headers['Authorization'] == null) {
      options.headers['Authorization'] = 'Bearer $_accessToken';
    }
    handler.next(options);
  }

  Future<void> _onError(DioException e, ErrorInterceptorHandler handler) async {
    // Réseau injoignable.
    if (e.type == DioExceptionType.connectionError ||
        e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout) {
      return handler.reject(
        DioException(
          requestOptions: e.requestOptions,
          error: const NetworkException(),
        ),
      );
    }

    final res = e.response;
    // Tentative unique de refresh sur 401.
    if (res?.statusCode == 401 &&
        !_refreshing &&
        e.requestOptions.path != '/v1/auth/refresh' &&
        e.requestOptions.extra['retried'] != true) {
      final ok = await _tryRefresh();
      if (ok) {
        final opts = e.requestOptions
          ..extra['retried'] = true
          ..headers['Authorization'] = 'Bearer $_accessToken';
        try {
          final clone = await _dio.fetch<dynamic>(opts);
          return handler.resolve(clone);
        } catch (_) {/* retombe dans le mapping ci-dessous */}
      }
    }

    handler.reject(
      DioException(
        requestOptions: e.requestOptions,
        response: res,
        error: _mapError(res),
      ),
    );
  }

  ApiException _mapError(Response<dynamic>? res) {
    final data = res?.data;
    if (data is Map) {
      return ApiException(
        statusCode: res?.statusCode ?? 0,
        code: (data['code'] as String?) ?? 'INTERNAL_ERROR',
        message: (data['message'] as String?) ?? '',
        details: data['details'],
      );
    }
    return ApiException(
      statusCode: res?.statusCode ?? 0,
      code: 'INTERNAL_ERROR',
      message: res?.statusMessage ?? '',
    );
  }

  Future<bool> _tryRefresh() async {
    final refresh = await _store.readRefreshToken();
    if (refresh == null) return false;
    _refreshing = true;
    try {
      final r = await _dio.post<Map<String, dynamic>>(
        '/v1/auth/refresh',
        data: {'refresh_token': refresh},
      );
      final body = r.data ?? const {};
      _accessToken = body['access_token'] as String?;
      final newRefresh = body['refresh_token'] as String?;
      if (newRefresh != null) await _store.writeRefreshToken(newRefresh);
      return _accessToken != null;
    } catch (_) {
      return false;
    } finally {
      _refreshing = false;
    }
  }

  // ---- helpers typés -------------------------------------------------------
  Future<Map<String, dynamic>> getJson(
    String path, {
    Map<String, dynamic>? query,
  }) async {
    final r = await _dio.get<Map<String, dynamic>>(path, queryParameters: query);
    return r.data ?? const {};
  }

  Future<Map<String, dynamic>> postJson(
    String path, {
    Object? body,
    String? idempotencyKey,
  }) async {
    final r = await _dio.post<Map<String, dynamic>>(
      path,
      data: body,
      options: idempotencyKey == null
          ? null
          : Options(headers: {'Idempotency-Key': idempotencyKey}),
    );
    return r.data ?? const {};
  }

  Future<void> delete(String path) => _dio.delete<void>(path);
}

final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(ref.watch(secureStoreProvider));
});
