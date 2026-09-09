/// Erreur normalisée : le backend renvoie `{ "code": "...", "message": "..." }`.
class ApiException implements Exception {
  ApiException({
    required this.statusCode,
    required this.code,
    required this.message,
    this.details,
  });

  final int statusCode;
  final String code;
  final String message;
  final Object? details;

  bool get isAuth => statusCode == 401 || code == 'INVALID_TOKEN';
  bool get isValidation => statusCode == 422 || code == 'VALIDATION_ERROR';

  /// Message présentable à l'utilisateur, à partir du `code` connu.
  String get friendly => switch (code) {
        'INVALID_CREDENTIALS' => 'Numéro ou code secret incorrect.',
        'INVALID_ACCOUNT_STATE' => 'Ce compte n\'est pas encore actif.',
        'OTP_INVALID' => 'Code de vérification incorrect ou expiré.',
        'INSUFFICIENT_FUNDS' => 'Solde insuffisant pour cette opération.',
        'RATE_LIMITED' => 'Trop de tentatives. Réessayez dans un instant.',
        'USER_FROZEN' => 'Votre compte est momentanément gelé.',
        'PHONE_NUMBER_ALREADY_LINKED' => 'Ce numéro est déjà utilisé.',
        _ => message.isNotEmpty ? message : 'Une erreur est survenue.',
      };

  @override
  String toString() => 'ApiException($statusCode, $code): $message';
}

/// Pas de réseau / timeout.
class NetworkException implements Exception {
  const NetworkException([this.cause]);
  final Object? cause;
  @override
  String toString() => 'NetworkException($cause)';
}
