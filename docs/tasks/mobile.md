# Tâches Mobile / Flutter (`MOB`)

Stack : Flutter 3 + Dart 3, Riverpod (état), go_router, dio + client généré depuis
`docs/api/openapi.json` (openapi-generator dart-dio), freezed/json_serializable,
flutter_secure_storage, local_auth (biométrie), mobile_scanner (QR), firebase_messaging
(push), intl (i18n FR/EN), thème bordeaux depuis `design/tokens.json`. Tests : flutter
test + integration_test, golden tests.

## Socle (MOB-001 → MOB-014)

- [ ] **MOB-001** · Init projet Flutter, organisation `lib/` (`core/`, `features/`,
  `shared/`), flavors `dev` / `staging` / `prod`, `--dart-define` pour `API_BASE_URL`.
- [ ] **MOB-002** · Thème : couleurs bordeaux + secondaire, typo, `ThemeData` clair/sombre
  générés depuis les tokens, composants Material 3 adaptés.
- [ ] **MOB-003** · Widgets de base : PrimaryButton, PinPad, AmountField, MoneyText,
  BottomSheet, SnackBar, Skeleton, EmptyState, ListRow, Avatar.
- [ ] **MOB-004** · Client API généré + intercepteurs dio (`Idempotency-Key`,
  `request_id`, refresh token, mapping `DomainError`), gestion hors‑ligne.
- [ ] **MOB-005** · Auth : stockage sécurisé des tokens, refresh, `authState` Riverpod,
  redirections go_router, verrouillage par PIN/biométrie à l'ouverture.
- [ ] **MOB-006** · Navigation : shell avec bottom nav (Accueil, Historique, QR, Carte,
  Profil), deep links (`flash://pay?...`, liens universels).
- [ ] **MOB-007** · i18n intl, FR par défaut, extraction ARB, formats monétaires/date.
- [ ] **MOB-008** · Gestion d'erreurs : widget d'erreur, retry, toasts mappés depuis
  `code`, écran hors‑ligne.
- [ ] **MOB-009** · Push : intégration firebase_messaging (gratuit), permission,
  enregistrement du token côté API, affichage en foreground, tap → route.
- [ ] **MOB-010** · Notifications in‑app temps réel : connexion SSE (ou fallback polling),
  badge, centre de notifications.
- [ ] **MOB-011** · Sécurité : détection appareil rooté/jailbreak (best effort), masquage
  du contenu en aperçu multitâche, timeout d'inactivité.
- [ ] **MOB-012** · Config CI build (voir `infra`) : `flutter analyze`, tests, build APK
  debug ; signatures et stores dans la phase INFRA.
- [ ] **MOB-013** · Accessibilité : Semantics, tailles de police dynamiques, contraste AA.
- [ ] **MOB-014** · Cache local (drift/sqflite ou hive) : dernier solde, dernières
  opérations, référentiel pays — lecture hors‑ligne.

## Parcours client (MOB-015 → MOB-036)

- [ ] **MOB-015** · Onboarding : numéro + pays, création PIN, OTP, écran succès.
- [ ] **MOB-016** · Connexion : numéro + PIN, biométrie, OTP nouvel appareil, PIN oublié.
- [ ] **MOB-017** · Accueil : solde(s) masquable, raccourcis (Envoyer, Payer, Retirer,
  Ajouter), dernières opérations, bandeau KYC.
- [ ] **MOB-018** · Envoyer : destinataire (contacts device + favoris + saisie), montant,
  aperçu frais 0,8 % + total, confirmation PIN/biométrie, reçu partageable.
- [ ] **MOB-019** · Demander de l'argent : créer, partager (lien/QR), listes reçues/émises.
- [ ] **MOB-020** · Scanner un QR marchand (mobile_scanner), QR dynamique, confirmation,
  reçu.
- [ ] **MOB-021** · Mon QR pour recevoir (montant optionnel), partage/plein écran.
- [ ] **MOB-022** · Retrait cash : générer le code, compte à rebours, annuler, statut.
- [ ] **MOB-023** · Dépôt cash : mon QR/identifiant à présenter à l'agent, notif à
  réception.
- [ ] **MOB-024** · Retrait/dépôt compte opérateur : choix opérateur, numéro, montant,
  frais, suivi asynchrone.
- [ ] **MOB-025** · Historique : liste paginée, filtres, recherche, groupé par jour,
  lecture hors‑ligne du cache.
- [ ] **MOB-026** · Détail + reçu : partage image/PDF, signaler, annuler si éligible.
- [ ] **MOB-027** · Coffre : poches, créer/renommer/supprimer, déplacer, poche verrouillée.
- [ ] **MOB-028** · Épargne : ouvrir un plan, progression, intérêts, versement manuel,
  clôture.
- [ ] **MOB-029** · Carte : demander, afficher (masqué + révéler sécurisé), geler/dégeler,
  plafonds, canaux, opérations.
- [ ] **MOB-030** · Mes numéros (max 5) : ajouter (OTP), principal, supprimer.
- [ ] **MOB-031** · Profil & KYC : upload pièce (caméra) + selfie, statut, limites.
- [ ] **MOB-032** · Notifications : centre, réglages push, historique.
- [ ] **MOB-033** · Sécurité : appareils, déconnexion à distance, changer PIN, activité.
- [ ] **MOB-034** · Paramètres : langue, pays, thème, masquer soldes, mentions légales.
- [ ] **MOB-035** · Partage de reçu natif (share_plus) image + PDF.
- [ ] **MOB-036** · Mode agent léger (si compte agent) : dépôt/retrait, code, float,
  commissions — écrans dédiés.

## Build & distribution (MOB-037 → MOB-044)

- [ ] **MOB-037** · Icône & splash Flash (flutter_native_splash, flutter_launcher_icons)
  aux couleurs bordeaux.
- [ ] **MOB-038** · Android : `applicationId`, permissions minimales, ProGuard, build
  release AAB.
- [ ] **MOB-039** · Signature Android (keystore via secrets CI), `key.properties` non
  commité.
- [ ] **MOB-040** · iOS : bundle id, capacités (caméra, push, biométrie), build IPA.
- [ ] **MOB-041** · Signature iOS (certs/profils via secrets CI ou fastlane match).
- [ ] **MOB-042** · Fastlane : lanes `beta` (Firebase App Distribution / TestFlight) et
  `release`.
- [ ] **MOB-043** · CI mobile : analyze + tests + golden + build artefacts par flavor.
- [ ] **MOB-044** · Écran « À propos » avec version/commit, lien conditions et
  confidentialité.

## Transverse

- [ ] **MOB-T1** · Tests widget + provider ≥ 75 % sur `features/`.
- [ ] **MOB-T2** · Golden tests des écrans clés (clair/sombre, FR).
- [ ] **MOB-T3** · integration_test : onboarding → transfert → retrait → historique.
