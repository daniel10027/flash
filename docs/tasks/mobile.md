# Tâches Mobile / Flutter (`MOB`)

Stack : Flutter 3 + Dart 3, Riverpod (état), go_router, dio + client généré depuis
`docs/api/openapi.json` (openapi-generator dart-dio), freezed/json_serializable,
flutter_secure_storage, local_auth (biométrie), mobile_scanner (QR), firebase_messaging
(push), intl (i18n FR/EN), thème bordeaux depuis `design/tokens.json`. Tests : flutter
test + integration_test, golden tests.

## Socle (MOB-001 → MOB-014)

- [x] **MOB-001** · projet `flutter create` (org `ci.flash`), `lib/{core,shared,features}`, flavors dev/staging/prod via `--dart-define` (`core/env/flavor.dart`).
- [x] **MOB-002** · thème Material 3 depuis `design/tokens.json` (bordeaux, clair+sombre, police Inter via `google_fonts`, transitions fade-through) — `core/theme/{tokens,app_theme,motion}.dart`.
- [x] **MOB-003** · widgets — `PrimaryButton` (press+loading), `PinPad` (haptique, shake d’erreur, biométrie), `AmountField` (aperçu frais 0,8 %), `MoneyText`, `GlassCard`, `BrandBackground` (aurore CustomPaint), `Skeleton/EmptyState/ListRow/Avatar`, `AppSnack`, `OfflineBanner`, `Pressable`.
- [x] **MOB-004** · `ApiClient` (dio) — `X-Request-ID`, `Idempotency-Key` auto, refresh 401 unique, mapping `ApiException`/`NetworkException`.
- [x] **MOB-005** · `AuthController` (unknown/signedOut/locked/signedIn) + `flutter_secure_storage`, `PinLockPage` (biométrie `local_auth` + code), déverrouillage via refresh token, redirections go_router.
- [x] **MOB-006** · `go_router` — `ShellRoute` bottom-nav 5 onglets, redirections onboarding/auth/lock.
- [x] **MOB-007** · `gen-l10n` FR (défaut) + EN (`l10n.yaml`, `lib/l10n/*.arb`).
- [x] **MOB-008** · `OfflineBanner` (`connectivity_plus`), `AppSnack` mappé sur `code`, états d’erreur avec retry sur le tableau de bord.
- [ ] **MOB-009** · Push : intégration firebase_messaging (gratuit), permission,
  enregistrement du token côté API, affichage en foreground, tap → route.
- [x] **MOB-010** · `unreadCountProvider` — flux SSE `GET /v1/notifications/stream` (dio `ResponseType.stream`, parse `data:`), rafraîchit liste + compteur ; repli polling 30 s ; `Badge` sur la cloche de l'accueil.
- [x] **MOB-011** · `AppLockGuard` — masquage du contenu en aperçu multitâche + re-verrouillage après 2 min d’inactivité en arrière-plan.
- [x] **MOB-012** · CI `mobile-ci.yml` livré avec `INFRA-009` (`dart format`, `flutter
  analyze`, `flutter test --coverage`, build APK debug flavor `dev`, artefacts).
- [x] **MOB-013** · passe a11y — `Semantics(button/label)` sur `Pressable` (raccourcis + grille de services), tailles de cibles ≥ 48, `MoneyText` en chiffres tabulaires.
- [x] **MOB-014** · cache lecture seule hors-ligne — `_cachedGet` met en cache les JSON `wallets` / `kyc` / `statement` et les rejoue sur `NetworkException` (`Prefs.cacheGet/Set`).

## Parcours client (MOB-015 → MOB-036)

- [x] **MOB-015** · `RegisterPage` — numéro → code → confirmation → OTP → succès, barre de progression, transitions slide/fade, animation de succès, câblé `/v1/auth/register` + `verify-otp`.
- [x] **MOB-016** · `WelcomePage` (`BrandBackground`) : connexion numéro/PIN en bottom sheet, lien « Créer un compte ».
- [x] **MOB-017** · `HomePage` — carte de solde dégradée avec montant animé (count-up), raccourcis, bandeau KYC tier 0, 5 dernières opérations (shimmer/EmptyState), pull-to-refresh ; providers `wallet/kyc/statement`. **Didacticiel** `shared/tutorial/coach_marks.dart` au 1er lancement.
- [x] **MOB-018** · `SendPage` — destinataire + `AmountField` (aperçu frais 0,8 %) + `ConfirmSheet` (friction PIN) + `ReceiptView` animée, `POST /v1/transfers`.
- [x] **MOB-019** · `RequestMoneyPage` — onglets Reçues / Émises (`GET /v1/payment-requests?direction`), créer + partager (`share_plus`), payer / refuser / annuler.
- [x] **MOB-020** · `ScanPage` (onglet Payer) — `mobile_scanner` + cadre de visée + saisie manuelle `flash://pay?m=…&c=…`, QR statique/dynamique, `POST /v1/merchant-payments`.
- [x] **MOB-021** · `ReceivePage` — `QrImageView` de `flash://pay?u=<id>&amount=<minor>`, partage `share_plus`, montant optionnel.
- [x] **MOB-022** · `WithdrawPage` — `POST /v1/withdrawals`, code plein écran + compte à rebours (`Timer`), annulation `/cancel`.
- [x] **MOB-023** · `DepositPage` — QR `flash://deposit?w=<id>` + identifiant sélectionnable à présenter à l'agent.
- [x] **MOB-024** · `OperatorPage` — `SegmentedButton` sens (vers opérateur / recharger Flash), choix opérateur, numéro + montant, `POST /v1/operators/<op>/{payout,topup}`, statut asynchrone.
- [x] **MOB-025** · `HistoryPage` — `GET /v1/statement` paginé (cursor), scroll infini, regroupé par jour (`intl` fr), pull-to-refresh, skeleton/EmptyState/erreur+retry.
- [x] **MOB-026** · `showOpDetail` — feuille reçu (`GET /v1/receipts/<ref>`) ouverte au tap sur une opération de l'historique.
- [x] **MOB-027** · `VaultPage` — `GET /v1/vault`, créer une poche, alimenter / retirer (`promptAmount`), verrouiller / déverrouiller.
- [x] **MOB-028** · `SavingsPage` — `GET /v1/savings/plans`, ouvrir un plan (objectif + taux), progression (`LinearProgressIndicator`), verser / retirer / clôturer.
- [x] **MOB-029** · `CardPage` — visuel carte dégradé, émettre, **révéler PAN/CVV 30 s** (`POST .../sensitive` + `Timer`), geler / dégeler.
- [x] **MOB-030** · `PhonesPage` — `GET /v1/phones`, ajout numéro + OTP (`POST /v1/phones` puis `/verify`), définir principal, supprimer ; « 5 max ».
- [x] **MOB-031** · `ProfilePage` — en-tête (avatar + id), carte KYC (palier + statut, upload **pièce + selfie** via `image_picker`, base64 → `POST /v1/kyc/submissions`), accès numéros / notifications / sécurité / paramètres / à propos, déconnexion.
- [x] **MOB-032** · `NotificationsPage` — `GET /v1/notifications`, marquage lu (`/read`, `/read-all`), pull-to-refresh, EmptyState.
- [x] **MOB-033** · `SecurityPage` — appareils connectés (`GET`/`DELETE /v1/auth/devices`), changer le code secret (`POST /v1/auth/change-pin`, 2 étapes), déconnexion.
- [x] **MOB-034** · `SettingsPage` — thème clair/sombre/auto, langue FR/EN/auto (`ThemeModeController` / `LocaleController` persistants), masquer les soldes par défaut.
- [x] **MOB-035** · partage natif du reçu (`share_plus`) depuis la feuille de détail et « Recevoir ».
- [x] **MOB-036** · `AgentPage` (visible dans le profil si `GET /v1/agent` répond) — float + commissions, dépôt client (`/v1/agent/deposits`), confirmation de retrait (`/v1/agent/withdrawals/confirm`).

## Build & distribution (MOB-037 → MOB-044)

- [x] **MOB-037** · icône (éclair bordeaux généré) + splash via `flutter_launcher_icons` / `flutter_native_splash`.
- [ ] **MOB-038** · Android : `applicationId`, permissions minimales, ProGuard, build
  release AAB.
- [ ] **MOB-039** · Signature Android (keystore via secrets CI), `key.properties` non
  commité.
- [ ] **MOB-040** · iOS : bundle id, capacités (caméra, push, biométrie), build IPA.
- [ ] **MOB-041** · Signature iOS (certs/profils via secrets CI ou fastlane match).
- [ ] **MOB-042** · Fastlane : lanes `beta` (Firebase App Distribution / TestFlight) et
  `release`.
- [ ] **MOB-043** · CI mobile : analyze + tests + golden + build artefacts par flavor.
- [x] **MOB-044** · `AboutPage` — version + build (`package_info_plus`), liens CGU / confidentialité / licences.

## Transverse

- [ ] **MOB-T1** · Tests widget + provider ≥ 75 % sur `features/`.
- [ ] **MOB-T2** · Golden tests des écrans clés (clair/sombre, FR).
- [ ] **MOB-T3** · integration_test : onboarding → transfert → retrait → historique.
