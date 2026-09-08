# ADR 0004 — Architecture multi‑pays

**Statut :** accepté · **Date :** 2026-09-08

## Contexte
Flash vise plusieurs pays (UEMOA au lancement : CI par défaut, puis SN, ML, BF, BJ… ;
CEMAC/XAF ensuite). Frais, limites, paliers KYC, devise, opérateurs et règles d'arrondi
diffèrent d'un pays à l'autre et **doivent pouvoir évoluer sans redéploiement**.

## Décision
- **Aucune valeur pays‑spécifique en dur** dans `domain/` ou `application/`. Le domaine
  reçoit un objet `Country` (et ses `PricingRule` / `LimitRule`) en paramètre.
- Référentiel en base :
  - `countries(code, currency, timezone, rounding_rule, default_operator,
    reversal_window)`
  - `operators(country_code, code, name, kind, enabled)`
  - `pricing_rules(country_code, operation, percent_bps, min_fee, max_fee, fixed_fee)` —
    transfert par défaut : `percent_bps = 80` (**0,8 %**)
  - `limits(country_code, kyc_tier, operation, per_tx, daily, monthly, balance_max)`
- Chargé au démarrage, **mis en cache Redis**, invalidé sur modification back‑office
  (événement `ReferenceDataChanged`). Un port `ReferenceDataProvider` expose le tout au
  reste de l'app.
- **Devise portée par le pays** : un wallet est créé dans la devise du pays de
  l'utilisateur. Les échanges inter‑devises (phase ultérieure) passent par un
  `RateProvider` et des postings `ROUNDING` pour les écarts d'arrondi.
- Le pays d'un utilisateur est fixé à l'inscription (déduit de l'indicatif du numéro
  principal, confirmable). Changement de pays = procédure encadrée (KYC, nouveau wallet),
  pas un simple champ éditable.
- Chaque montant, limite et frais est **toujours** manipulé comme `Money` (donc lié à une
  devise) — jamais un entier nu.

## Conséquences
- Ouvrir un pays = insérer des lignes de référentiel + activer des opérateurs, sans
  toucher au code métier. Prouvé par un test paramétrant CI et SN différemment.
- La grille tarifaire (dont le 0,8 %) est éditable par la conformité via le back‑office,
  avec journal d'audit immuable des changements.
