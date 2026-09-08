# ADR 0001 — Choix de la stack

**Statut :** accepté · **Date :** 2026-09-08

## Contexte
Flash = plateforme de monnaie électronique : API centrale, web client + agent +
back‑office, application mobile client. Contraintes : hébergement sur un VPS unique,
budget notifications nul, équipe qui connaît Python/Flask, React, Flutter.

## Décision
- **Backend : Python 3.12 + Flask** (app factory, blueprints). Flask est volontairement
  minimal → l'architecture hexagonale porte la structure, pas le framework.
  SQLAlchemy 2 (core + mapping impératif), Alembic, PostgreSQL 16, Redis 7
  (idempotence, OTP, rate‑limit, verrous, pub/sub SSE), gunicorn.
- **Web : React 18 + Vite + TypeScript**, TanStack Query, React Router, client API
  généré depuis l'OpenAPI. PWA.
- **Mobile : Flutter 3 + Dart 3**, Riverpod, go_router, dio + client généré, Firebase
  Cloud Messaging pour le push (gratuit).
- **Notifications gratuites :** FCM (push mobile + web), SMTP (email), SSE maison
  (in‑app). SMS : adapter avec implémentation console en dev ; en prod, brancher un
  fournisseur payant (hors périmètre logiciel).
- **Emballage :** Docker partout. `docker compose` en dev et en prod (VPS).
  Reverse proxy **Caddy** (TLS automatique).
- **CI/CD :** GitHub Actions (lint, tests, build images GHCR, déploiement SSH).

## Conséquences
- Un seul langage backend, testable sans I/O grâce à l'hexagonal.
- Pas de dépendance à un cloud manager → portable, mais la HA est limitée (VPS unique) :
  acceptable au lancement, réévalué si le volume grimpe (cf. ADR futur « scale‑out »).
- Le client API généré évite la dérive front/back ; un job CI vérifie l'OpenAPI.
