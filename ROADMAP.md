# Flash — Map de développement

> **Dernière mise à jour : 2026-09-08**
> **Session courante : Phase 1 backend terminée (BE-001 → BE-024) + INFRA-001/002.**
> Domaine complet (identity, wallet, ledger partie double, pricing 0,8 %, limits) +
> application (UseCase, UoW, idempotence) + infrastructure (config env, SQLAlchemy +
> mappers, `SqlAlchemyUnitOfWork` + dépôts + outbox, Alembic + migration initiale,
> adapters clock/UUIDv7/Argon2/Redis) + interface Flask (app factory, `/health`,
> `DomainError`→HTTP, logs JSON, CORS ; **JWT** access/refresh rotatif + révocation +
> **rate-limit** Redis ; **OpenAPI 3.1** + `/docs` + `/redoc` + `flash openapi dump`) +
> **test d'architecture** (domaine pur, vérifié par AST). CLI `flash db|openapi|serve`.
> Docker : stack `docker compose up` vérifiée de bout en bout.
> 292 tests unit + 6 d'intégration (Postgres réel), couverture 100 % domain+application,
> ruff + mypy stricts, `docs/api/openapi.json` généré.
> **Prochaine : Phase 2 — BE-025 `RegisterUser` + blueprint `auth`, puis BE-026/027
> (OTP, login), BE-028 (numéros), BE-030/031 (wallet, transfert P2P).**

Ce fichier est la vue d'ensemble. Le détail (une ligne = une tâche cochable) est dans
`docs/tasks/`. On avance **dans l'ordre des identifiants** à l'intérieur de chaque lot,
mais les lots Backend / Infra avancent en priorité car Web et Mobile en dépendent.

## Comment lire / mettre à jour

- `[ ]` = à faire · `[~]` = en cours (commencée, pas finie) · `[x]` = terminée + testée
- Ne jamais cocher `[x]` sans : code complet, tests verts, doc à jour, pas de `TODO`.
- Après chaque tâche : cocher ici **et** dans le fichier `docs/tasks/*.md` correspondant,
  puis actualiser la date et la ligne « Session courante » ci‑dessus.

## Avancement global

| Lot | Fichier détaillé | Fait / Total |
|-----|------------------|--------------|
| Fondations & docs | ce fichier | 6 / 6 |
| Backend (BE) | [docs/tasks/backend.md](docs/tasks/backend.md) | 24 / 78 |
| Web (WEB) | [docs/tasks/frontend-web.md](docs/tasks/frontend-web.md) | 0 / 46 |
| Mobile (MOB) | [docs/tasks/mobile.md](docs/tasks/mobile.md) | 0 / 44 |
| Infra & CI/CD (INFRA) | [docs/tasks/infra.md](docs/tasks/infra.md) | 2 / 24 |
| Design & marque (DSN) | [docs/tasks/design.md](docs/tasks/design.md) | 0 / 10 |

---

## Phase 0 — Fondations (en cours)

- [x] F0‑1 · Structure du monorepo (`backend web mobile infra design docs`)
- [x] F0‑2 · `README.md` + principes non négociables
- [x] F0‑3 · Cette map + fichiers de tâches détaillés
- [x] F0‑4 · `docs/architecture.md` (architecture hexagonale, couches, flux)
- [x] F0‑5 · `docs/domain-model.md` (entités, invariants, agrégats, événements)
- [x] F0‑6 · ADR 0001‑0004 (stack, hexagonal, ledger partie double, multi‑pays)

## Phase 1 — Socle backend

Domaine partagé (Money, Currency, Country), identité (User, PhoneNumber ≤ 5), wallet,
**ledger partie double**, ports, config multi‑pays, app factory Flask, Postgres + Alembic,
auth (téléphone + PIN + OTP, JWT), erreurs & idempotence, tests unitaires du domaine.
→ `BE-001` à `BE-024`.

## Phase 2 — Cas d'usage cœur

Ouverture de compte, KYC par paliers, transfert P2P (frais 0,8 %), paiement marchand par
QR, dépôt cash agent, retrait cash agent (code de retrait), annulation / remboursement,
relevé & historique paginé, notifications (push FCM / email / in‑app SSE).
→ `BE-025` à `BE-046`.

## Phase 3 — Produits d'épargne & carte

Coffre (sous‑comptes verrouillables), objectifs d'épargne, épargne programmée & intérêts,
carte virtuelle (émission, gel, plafonds, tokenisation), rapprochement carte.
→ `BE-047` à `BE-060`.

## Phase 4 — Multi‑pays, marchands, agents, back‑office

Référentiel pays / opérateurs / grille tarifaire, interopérabilité (Orange/MTN/Moov via
adapters), comptes marchands & règlements, réseau d'agents (float, commissions, plafonds),
console d'administration (support, conformité, litiges), export réglementaire.
→ `BE-061` à `BE-078`.

## Phase 5 — Web (React)

Auth, tableau de bord, transfert, QR (scan + présenter), historique + reçus, coffre,
épargne, carte, gestion des 5 numéros, profil / KYC, **espace agent** (dépôt/retrait,
float, commissions), **back‑office** (rôles). i18n FR (+ EN), thème bordeaux, PWA.
→ `WEB-001` à `WEB-046`.

## Phase 6 — Mobile (Flutter)

Mêmes parcours client que le web + scan QR natif, biométrie, notifications push,
mode hors‑ligne lecture, deep links, build Android/iOS, signature.
→ `MOB-001` à `MOB-044`.

## Phase 7 — Industrialisation

CI complète (lint, tests, couverture, images), CD VPS (compose + Caddy + sauvegardes PG),
observabilité (logs JSON, métriques, /health), tests d'intégration & E2E, tests de
charge, revue sécurité (OWASP ASVS, secrets, rate‑limit), doc API publiée, runbook.
→ `INFRA-001` à `INFRA-024`, `BE` tests transverses.

---

## Prochaine action

**Phase 2.** `BE-025` — cas d'usage `RegisterUser` (msisdn + PIN + pays → `User` tier 0
+ wallet devise du pays + compte ledger client, OTP d'activation, idempotent) et le
blueprint `auth` (`POST /v1/auth/register`) avec ses schémas pydantic et sa doc OpenAPI.
Puis `BE-026` (VerifyOtp/ResendOtp + port `OtpChannel` console/SMS), `BE-027` (Login /
Refresh / Logout via `TokenService`), `BE-028` (ajout/suppression/promotion de numéro),
`BE-030` (GetWallet/ListWallets), `BE-031` (`SendP2PTransfer`, frais 0,8 %).
