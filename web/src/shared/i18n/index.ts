// WEB-007 — i18n. FR par défaut ; EN prévu (fichier à ajouter). La langue est
// persistée et retombe sur la préférence navigateur.
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import { fr } from './fr';

const STORAGE_KEY = 'flash.lang';
export const SUPPORTED = ['fr'] as const;
export type Lang = (typeof SUPPORTED)[number];

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(STORAGE_KEY) as Lang | null;
    if (saved && SUPPORTED.includes(saved)) return saved;
  } catch {
    /* ignore */
  }
  const nav = (navigator.language || 'fr').slice(0, 2) as Lang;
  return SUPPORTED.includes(nav) ? nav : 'fr';
}

void i18n.use(initReactI18next).init({
  resources: { fr: { translation: fr } },
  lng: initialLang(),
  fallbackLng: 'fr',
  interpolation: { escapeValue: false },
  returnNull: false,
});

export function setLang(lang: Lang): void {
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    /* ignore */
  }
  void i18n.changeLanguage(lang);
}

export { i18n };
