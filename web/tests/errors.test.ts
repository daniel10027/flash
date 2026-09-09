import { describe, expect, it } from 'vitest';
import { ApiError, friendlyMessage, NetworkError } from '@shared/api/errors';

describe('ApiError', () => {
  it('expose code / status / details et un message convivial mappé', () => {
    const err = new ApiError(422, {
      code: 'INSUFFICIENT_FUNDS',
      message: 'Solde insuffisant pour réaliser cette opération.',
      details: { available_minor: 100 },
    });
    expect(err.is('INSUFFICIENT_FUNDS')).toBe(true);
    expect(err.status).toBe(422);
    expect(err.details.available_minor).toBe(100);
    expect(friendlyMessage(err)).toBe('Solde insuffisant pour cette opération.');
  });

  it('retombe sur le message serveur pour un code inconnu', () => {
    const err = new ApiError(422, { code: 'WEIRD_CODE', message: 'Message serveur.' });
    expect(friendlyMessage(err)).toBe('Message serveur.');
  });

  it('gère les erreurs réseau', () => {
    expect(friendlyMessage(new NetworkError())).toMatch(/serveur/i);
  });
});
