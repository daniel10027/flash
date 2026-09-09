// WEB-004 / WEB-008 — modèle d'erreur API aligné sur docs/api/errors.md.

export type ApiErrorBody = {
  code: string;
  message: string;
  details?: Record<string, unknown>;
};

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message || body.code);
    this.name = 'ApiError';
    this.code = body.code;
    this.status = status;
    this.details = body.details ?? {};
  }

  is(code: string): boolean {
    return this.code === code;
  }
}

export class NetworkError extends Error {
  constructor() {
    super('Impossible de joindre le serveur.');
    this.name = 'NetworkError';
  }
}

// Libellés d'action côté client. Le message serveur reste le repli.
const FRIENDLY: Record<string, string> = {
  INSUFFICIENT_FUNDS: 'Solde insuffisant pour cette opération.',
  LIMIT_EXCEEDED: 'Plafond atteint. Vérifiez votre niveau de vérification.',
  KYC_REQUIRED: 'Vérifiez votre identité pour débloquer cette opération.',
  RECIPIENT_NOT_FOUND: 'Aucun compte Flash pour ce numéro.',
  SELF_TRANSFER: 'Vous ne pouvez pas vous envoyer de l’argent à vous-même.',
  DUPLICATE_OPERATION: 'Cette opération a déjà été traitée.',
  RATE_LIMITED: 'Trop de tentatives. Réessayez dans un instant.',
  OTP_INVALID: 'Code de vérification incorrect.',
  OTP_TOO_MANY_ATTEMPTS: 'Trop d’essais. Demandez un nouveau code.',
  INVALID_CREDENTIALS: 'Numéro ou code secret incorrect.',
  UNAUTHENTICATED: 'Session expirée. Reconnectez-vous.',
  INVALID_TOKEN: 'Session invalide. Reconnectez-vous.',
  VALIDATION_ERROR: 'Certains champs sont invalides.',
  INTERNAL_ERROR: 'Une erreur est survenue. Réessayez plus tard.',
};

export function friendlyMessage(error: unknown): string {
  if (error instanceof ApiError) return FRIENDLY[error.code] ?? error.message;
  if (error instanceof NetworkError) return error.message;
  if (error instanceof Error) return error.message;
  return 'Une erreur inattendue est survenue.';
}
