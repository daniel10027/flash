// Repli de configuration runtime pour le dev, `npm run preview` et l'audit Lighthouse.
// L'image Docker écrase ce fichier au démarrage (voir docker-entrypoint.sh).
window.__FLASH_CONFIG__ = {
  API_BASE_URL: '',
  ENV: 'development',
  SENTRY_DSN: '',
};
