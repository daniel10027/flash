import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@shared/theme/global.css';
import '@app/theme'; // applique le thème avant le premier rendu
import '@shared/i18n';
import { AppProviders } from '@app/providers';
import { AppRouter } from '@app/router';
import { registerPwa } from './pwa';

registerPwa();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AppProviders>
      <AppRouter />
    </AppProviders>
  </StrictMode>,
);
