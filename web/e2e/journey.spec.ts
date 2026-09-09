import { expect, test, type Page, type Route } from '@playwright/test';

// Saisit un code dans un groupe <PinInput> : le focus avance tout seul d'un champ
// à l'autre, on tape donc la séquence dans le premier chiffre.
async function fillPin(page: Page, code: string) {
  const first = page.getByLabel('Chiffre 1');
  await first.click();
  await first.pressSequentially(code, { delay: 20 });
}

// WEB-T2 — parcours de bout en bout : inscription → dépôt agent → transfert →
// retrait → paiement marchand. L'API est simulée par une petite banque en mémoire
// (état mutable) pour rester hermétique ; chaque écran réel est traversé.

type Json = Record<string, unknown>;

function installApi(routeAll: (matcher: string, h: (r: Route) => Promise<void>) => Promise<void>) {
  const state = {
    balance: 0, // unité mineure XOF
    walletId: 'wlt_1',
    tokens: () => ({
      access_token: 'access-' + Date.now(),
      refresh_token: 'refresh-1',
      access_expires_in: 900,
      refresh_expires_in: 2_592_000,
      user_id: 'usr_1',
    }),
  };

  const json = (route: Route, body: Json | unknown, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

  return routeAll('**/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const method = route.request().method();
    const post = () => {
      try {
        return JSON.parse(route.request().postData() || '{}') as Json;
      } catch {
        return {} as Json;
      }
    };

    // --- auth
    if (path.endsWith('/v1/auth/register') && method === 'POST')
      return json(route, { user_id: 'usr_1', activation_required: true });
    if (path.endsWith('/v1/auth/verify-otp') && method === 'POST')
      return json(route, state.tokens());
    if (path.endsWith('/v1/auth/refresh') && method === 'POST') return json(route, state.tokens());
    if (path.endsWith('/v1/auth/login') && method === 'POST') return json(route, state.tokens());

    // --- lectures tableau de bord
    if (path.endsWith('/v1/wallets'))
      return json(route, {
        wallets: [
          {
            id: state.walletId,
            currency: 'XOF',
            available_minor: state.balance,
            reserved_minor: 0,
            balance_minor: state.balance,
            status: 'ACTIVE',
          },
        ],
      });
    if (path.endsWith('/v1/kyc/status')) return json(route, { tier: 1, status: 'VERIFIED' });
    if (path.endsWith('/v1/statement')) return json(route, { lines: [], next_cursor: null });
    if (path.endsWith('/v1/notifications')) return json(route, { notifications: [], unread: 0 });

    // --- espace agent
    if (path.endsWith('/v1/agent'))
      return json(route, {
        agent_id: 'agt_1',
        status: 'ACTIVE',
        currency: 'XOF',
        float_available_minor: 5_000_000,
        commission_earned_minor: 0,
        commission_paid_minor: 0,
        commission_owed_minor: 0,
      });
    if (path.endsWith('/v1/agent/customers')) return json(route, { customers: [] });
    if (path.endsWith('/v1/agent/operations')) return json(route, { operations: [] });
    if (path.endsWith('/v1/agent/deposits') && method === 'POST') {
      // le dépôt agent crédite le client — ici, le compte courant, pour le parcours
      state.balance += Number(post().amount_minor ?? 0);
      return json(route, {
        operation: 'deposit',
        amount_minor: post().amount_minor,
        client_balance_minor: state.balance,
      });
    }

    // --- transfert P2P (frais 0,8 %)
    if (path.endsWith('/v1/transfers') && method === 'POST') {
      const amount = Number(post().amount_minor ?? 0);
      const fee = Math.ceil((amount * 80) / 10_000);
      state.balance -= amount + fee;
      return json(route, {
        reference: 'TRF-1',
        amount_minor: amount,
        fee_minor: fee,
        status: 'COMPLETED',
        recipient: post().recipient_phone_number,
      });
    }

    // --- retrait cash
    if (path.endsWith('/v1/withdrawals') && method === 'POST') {
      const amount = Number(post().amount_minor ?? 0);
      const fee = Math.ceil((amount * 100) / 10_000);
      state.balance -= amount + fee;
      return json(route, {
        order_id: 'ord_1',
        code: '482913',
        amount_minor: amount,
        fee_minor: fee,
        currency: 'XOF',
        status: 'PENDING',
        expires_at: new Date(Date.now() + 300_000).toISOString(),
      });
    }

    // --- paiement marchand
    if (path.endsWith('/v1/merchant-payments') && method === 'POST') {
      const amount = Number(post().amount_minor ?? 0);
      state.balance -= amount;
      return json(route, {
        reference: 'MPY-1',
        amount_minor: amount,
        fee_minor: 0,
        status: 'PAID',
        merchant_id: post().merchant_id,
      });
    }

    return json(route, {});
  });
}

test.use({ serviceWorkers: 'block' });

test('parcours complet : inscription → dépôt agent → transfert → retrait → paiement marchand', async ({
  page,
}) => {
  await installApi((m, h) => page.route(m, h));

  // 1) Inscription
  await page.goto('/register');
  await page.getByLabel('Numéro de téléphone').fill('+2250700000123');
  await fillPin(page, '2468');
  await page.getByRole('button', { name: 'Continuer' }).click();
  await fillPin(page, '2468');
  await page.getByRole('button', { name: 'Créer le compte' }).click();
  await fillPin(page, '000000');
  await page.getByRole('button', { name: 'Valider' }).click();
  // la session est ouverte : `RedirectIfAuthed` renvoie /register vers le tableau de bord
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole('navigation', { name: 'Raccourcis' })).toBeVisible();

  // 2) Dépôt agent (approvisionne le compte : 200 000)
  await page.goto('/agent/deposit');
  await page.getByLabel('Numéro du client').fill('+2250700000123');
  await page.getByLabel('Montant').fill('200000');
  await page.getByRole('button', { name: 'Encaisser et créditer' }).click();
  await expect(page.getByRole('heading', { name: 'Reçu de dépôt' })).toBeVisible();

  // Le tableau de bord reflète le solde crédité.
  await page.goto('/');
  await expect(page.locator('#main').getByText(/200[\s\u00a0\u202f]000/)).toBeVisible();

  // 3) Transfert P2P depuis un raccourci du tableau de bord
  await page
    .getByRole('navigation', { name: 'Raccourcis' })
    .getByRole('link', { name: 'Envoyer' })
    .click();
  await expect(page).toHaveURL(/\/send$/);
  await page.getByLabel('Numéro du destinataire').fill('+2250700000999');
  await page.getByLabel('Montant').fill('50000');
  await expect(page.getByText(/Frais \(0,8 %\)/)).toBeVisible();
  await page.getByRole('button', { name: 'Continuer' }).click();
  await fillPin(page, '2468');
  await page.getByRole('button', { name: 'Confirmer' }).click();
  await expect(page.getByRole('heading', { name: 'Reçu' })).toBeVisible();

  // solde : 200 000 - 50 000 - 400 (0,8 %) = 149 600
  await page.goto('/');
  await expect(page.locator('#main').getByText(/149[\s\u00a0\u202f]600/)).toBeVisible();

  // 4) Retrait cash
  await page.goto('/cash/withdraw');
  await page.getByLabel('Montant').fill('20000');
  await page.getByRole('button', { name: 'Générer le code' }).click();
  await expect(page.getByRole('heading', { name: 'Code de retrait' })).toBeVisible();
  await expect(page.getByText('482913')).toBeVisible();

  // 5) Paiement marchand (saisie du code)
  await page.goto('/pay');
  await page.getByLabel('Code marchand').fill('flash://pay?m=mrc_42');
  await page.getByRole('button', { name: 'Utiliser ce code' }).click();
  await page.getByLabel('Montant').fill('10000');
  await page.getByRole('button', { name: 'Payer' }).click();
  await fillPin(page, '2468');
  await page.getByRole('button', { name: 'Confirmer' }).click();
  await expect(page.getByRole('heading', { name: 'Reçu' })).toBeVisible();

  // solde final : 149 600 - 20 000 - 200 (retrait) - 10 000 = 119 400
  await page.goto('/');
  await expect(page.locator('#main').getByText(/119[\s\u00a0\u202f]400/)).toBeVisible();
});
