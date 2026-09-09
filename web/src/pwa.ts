// WEB-009 — enregistrement du service worker + invite de mise à jour légère.
import { registerSW } from 'virtual:pwa-register';
import { toast } from '@shared/ui';

export function registerPwa(): void {
  if (import.meta.env.DEV) return;
  const updateSW = registerSW({
    onNeedRefresh() {
      toast.info('Une nouvelle version est disponible — rechargez la page.');
      void updateSW(true);
    },
    onOfflineReady() {
      toast.success('Flash est prêt à fonctionner hors-ligne (lecture).');
    },
  });
}
