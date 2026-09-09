import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import 'wallet_models.dart';

/// Portefeuille principal (le premier renvoyé par l'API).
final primaryWalletProvider = FutureProvider<Wallet?>((ref) async {
  final api = ref.watch(apiClientProvider);
  final r = await api.getJson('/v1/wallets');
  final list = (r['wallets'] as List?) ?? const [];
  if (list.isEmpty) return null;
  return Wallet.fromJson(list.first as Map<String, dynamic>);
});

final kycStatusProvider = FutureProvider<KycStatus>((ref) async {
  final api = ref.watch(apiClientProvider);
  return KycStatus.fromJson(await api.getJson('/v1/kyc/status'));
});

/// 5 dernières opérations pour le tableau de bord.
final recentStatementProvider =
    FutureProvider<List<StatementLine>>((ref) async {
  final api = ref.watch(apiClientProvider);
  final r = await api.getJson('/v1/statement', query: {'limit': 5});
  final lines = (r['lines'] as List?) ?? const [];
  return lines
      .map((e) => StatementLine.fromJson(e as Map<String, dynamic>))
      .toList();
});

/// Rafraîchit tout le tableau de bord (pull-to-refresh).
void refreshDashboard(WidgetRef ref) {
  ref
    ..invalidate(primaryWalletProvider)
    ..invalidate(kycStatusProvider)
    ..invalidate(recentStatementProvider);
}
