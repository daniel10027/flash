// Appels d'authentification. Le parcours complet (WEB-013/014) affinera ceci ;
// le socle fournit login + OTP suffisants pour établir une session.
import { api } from '@shared/api/client';
import { deviceId, type TokenPair } from '@shared/auth/session';

export type LoginInput = { phone_number: string; country: string; pin: string };

type LoginResult = { kind: 'authenticated'; tokens: TokenPair } | { kind: 'otp_required' };

export async function login(input: LoginInput): Promise<LoginResult> {
  const res = await api.post<Record<string, unknown>>('/v1/auth/login', input);
  if (res && typeof res.access_token === 'string') {
    return { kind: 'authenticated', tokens: res as unknown as TokenPair };
  }
  return { kind: 'otp_required' };
}

export async function verifyOtp(input: {
  phone_number: string;
  country: string;
  code: string;
}): Promise<TokenPair> {
  return api.post<TokenPair>('/v1/auth/verify-otp', { ...input, device_id: deviceId() });
}

export async function resendOtp(input: { phone_number: string; country: string }): Promise<void> {
  await api.post('/v1/auth/resend-otp', input);
}
