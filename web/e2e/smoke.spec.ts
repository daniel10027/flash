import { expect, test } from '@playwright/test';

// WEB-001 (socle) — fumée : l'app se charge, redirige vers /login pour un visiteur
// non authentifié, et la galerie UI répond.
test('redirige un visiteur vers la connexion', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { name: 'Se connecter' })).toBeVisible();
});

test('404 pour une route inconnue', async ({ page }) => {
  await page.goto('/route-qui-nexiste-pas');
  await expect(page).toHaveURL(/\/404$/);
  await expect(page.getByRole('heading', { name: '404' })).toBeVisible();
});

test('le formulaire de connexion valide la saisie', async ({ page }) => {
  await page.goto('/login');
  const submit = page.getByRole('button', { name: 'Continuer' });
  await expect(submit).toBeDisabled();
  await page.getByLabel('Numéro de téléphone').fill('+2250700000101');
  for (const [i, d] of [...'1397'].entries()) {
    await page.getByLabel(`Chiffre ${i + 1}`).fill(d);
  }
  await expect(submit).toBeEnabled();
});

test('la connexion propose la création de compte', async ({ page }) => {
  await page.goto('/login');
  await page.getByRole('link', { name: 'Créer un compte' }).click();
  await expect(page).toHaveURL(/\/register$/);
  await expect(page.getByRole('heading', { name: 'Créer un compte' })).toBeVisible();
});
