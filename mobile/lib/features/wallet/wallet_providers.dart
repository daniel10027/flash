import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../../core/network/api_exception.dart';
import '../../core/storage/prefs.dart';
import 'wallet_models.dart';

/// Récupère un JSON, le met en cache, et retombe sur le cache si le réseau
/// manque (MOB-014 — lecture seule hors-ligne).
Future<Map<String, dynamic>> _cachedGet(
  Ref ref,
  String path, {
  Map<String, dynamic>? query,
  required String cacheKey,
}) async {
  final prefs = ref.read(prefsProvider);
  try {
    final r = await ref.watch(apiClientProvider).getJson(path, query: query);
    await prefs.cacheSet(cacheKey, jsonEncode(r));
    return r;
  } on NetworkException {
    final cached = prefs.cacheGet(cacheKey);
    if (cached != null) return jsonDecode(cached) as Map<String, dynamic>;
    rethrow;
  }
}

final primaryWalletProvider = FutureProvider<Wallet?>((ref) async {
  final r = await _cachedGet(ref, '/v1/wallets', cacheKey: 'wallets');
  final list = (r['wallets'] as List?) ?? const [];
  if (list.isEmpty) return null;
  return Wallet.fromJson(list.first as Map<String, dynamic>);
});

final kycStatusProvider = FutureProvider<KycStatus>((ref) async {
  return KycStatus.fromJson(
    await _cachedGet(ref, '/v1/kyc/status', cacheKey: 'kyc'),
  );
});

final recentStatementProvider =
    FutureProvider<List<StatementLine>>((ref) async {
  final r = await _cachedGet(
    ref,
    '/v1/statement',
    query: {'limit': 5},
    cacheKey: 'statement5',
  );
  final lines = (r['lines'] as List?) ?? const [];
  return lines
      .map((e) => StatementLine.fromJson(e as Map<String, dynamic>))
      .toList();
});

void refreshDashboard(WidgetRef ref) {
  ref
    ..invalidate(primaryWalletProvider)
    ..invalidate(kycStatusProvider)
    ..invalidate(recentStatementProvider);
}
