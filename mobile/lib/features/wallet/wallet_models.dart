/// DTO minces (écrits à la main — pas de codegen). Tolérants aux champs
/// manquants pour rester robustes aux évolutions de l'API.
class Wallet {
  Wallet({
    required this.id,
    required this.currency,
    required this.availableMinor,
    required this.reservedMinor,
    required this.status,
  });

  factory Wallet.fromJson(Map<String, dynamic> j) => Wallet(
        id: j['id'] as String? ?? '',
        currency: j['currency'] as String? ?? 'XOF',
        availableMinor: (j['available_minor'] as num?)?.toInt() ?? 0,
        reservedMinor: (j['reserved_minor'] as num?)?.toInt() ?? 0,
        status: j['status'] as String? ?? 'ACTIVE',
      );

  final String id;
  final String currency;
  final int availableMinor;
  final int reservedMinor;
  final String status;
}

class KycStatus {
  KycStatus({required this.tier, required this.label});

  factory KycStatus.fromJson(Map<String, dynamic> j) => KycStatus(
        tier: (j['tier'] as num?)?.toInt() ??
            (j['kyc_tier'] as num?)?.toInt() ??
            0,
        label: j['status'] as String? ?? 'UNVERIFIED',
      );

  final int tier;
  final String label;
}

class StatementLine {
  StatementLine({
    required this.id,
    required this.kind,
    required this.direction,
    required this.amountMinor,
    required this.currency,
    required this.reference,
    required this.occurredAt,
    this.counterparty,
  });

  factory StatementLine.fromJson(Map<String, dynamic> j) => StatementLine(
        id: j['id'] as String? ?? '',
        kind: j['kind'] as String? ?? 'OP',
        direction: j['direction'] as String? ?? 'out',
        amountMinor: (j['amount_minor'] as num?)?.toInt() ?? 0,
        currency: j['currency'] as String? ?? 'XOF',
        reference: j['reference'] as String? ?? '',
        occurredAt: DateTime.tryParse(j['occurred_at'] as String? ?? '') ??
            DateTime.now(),
        counterparty: j['counterparty_masked'] as String?,
      );

  final String id;
  final String kind;
  final String direction;
  final int amountMinor;
  final String currency;
  final String reference;
  final DateTime occurredAt;
  final String? counterparty;

  /// Montant signé pour l'affichage (négatif si sortie).
  int get signedMinor => direction == 'out' ? -amountMinor : amountMinor;
}
