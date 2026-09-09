// WEB-011 — configuration runtime injectée par l'image (window.__FLASH_CONFIG__),
// avec repli sur les variables Vite en développement.

export type RuntimeConfig = {
  API_BASE_URL: string;
  ENV: 'development' | 'staging' | 'production';
  SENTRY_DSN: string;
};

declare global {
  interface Window {
    __FLASH_CONFIG__?: Partial<RuntimeConfig>;
  }
}

const injected = (typeof window !== 'undefined' && window.__FLASH_CONFIG__) || {};

export const config: RuntimeConfig = {
  API_BASE_URL: injected.API_BASE_URL ?? import.meta.env.VITE_API_BASE_URL ?? '',
  ENV: (injected.ENV ?? import.meta.env.MODE ?? 'development') as RuntimeConfig['ENV'],
  SENTRY_DSN: injected.SENTRY_DSN ?? import.meta.env.VITE_SENTRY_DSN ?? '',
};

export const isProd = config.ENV === 'production';
