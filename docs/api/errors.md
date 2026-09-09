# Codes d'erreur de l'API Flash

> Généré/maintenu au fil de l'eau. La complétude est vérifiée par
> `backend/tests/interface/test_errors_doc.py` (BE-T5) : tout `code` renvoyable par
> l'API figure dans ce document, sinon la CI casse.

## Enveloppe

Toute réponse d'erreur a le même corps JSON :

```json
{
  "code": "SCREAMING_SNAKE_CASE",
  "message": "Message lisible en français.",
  "details": { }
}
```

- `code` — identifiant **stable**, sûr à tester côté client. Ne change jamais de sens.
- `message` — texte FR destiné à l'affichage ; peut évoluer.
- `details` — objet libre, présent selon le code (montants, plafonds, champs invalides…).

L'en-tête `X-Request-ID` est renvoyé sur **toutes** les réponses (erreurs comprises) pour
le rapprochement avec les logs.

## Statuts HTTP

| Statut | Sens |
|---|---|
| `400` | Requête malformée (JSON illisible, en-tête obligatoire absent). |
| `401` | Authentification absente, invalide ou expirée. |
| `403` | Authentifié mais non autorisé (rôle back-office insuffisant). |
| `404` | Ressource ou contrepartie introuvable. |
| `409` | Conflit : l'état courant interdit l'opération, ou rejeu d'une opération. |
| `422` | Requête bien formée mais **règle métier** non satisfaite (statut par défaut). |
| `429` | Trop de requêtes (rate-limit) ou trop de tentatives OTP. |
| `500` | Erreur interne non prévue. `details` toujours vide. |

Toute `DomainError` non listée dans la table de correspondance retombe sur **422**.

---

## Erreurs transverses (couche interface)

| `code` | HTTP | Quand |
|---|---|---|
| `UNAUTHENTICATED` | 401 | Aucun jeton d'accès fourni sur une route protégée. |
| `INVALID_TOKEN` | 401 | Jeton d'accès illisible, signature invalide ou expiré. |
| `VALIDATION_ERROR` | 422 | Le corps de requête ne respecte pas le schéma (`details.fields[]`). |
| `RATE_LIMITED` | 429 | Quota de requêtes dépassé pour cette route / ce sujet. |
| `INTERNAL_ERROR` | 500 | Exception non gérée. À corréler via `X-Request-ID`. |
| `NOT_FOUND` | 404 | Chemin inconnu (route inexistante). |
| `METHOD_NOT_ALLOWED` | 405 | Méthode HTTP non supportée sur ce chemin. |
| `BAD_REQUEST` | 400 | Corps JSON illisible ou en-tête obligatoire manquant. |

> `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `BAD_REQUEST` proviennent des `HTTPException`
> Werkzeug ; le `code` est dérivé du nom de l'exception (`error.name` normalisé).

---

## Saisie & argent

| `code` | HTTP | Quand |
|---|---|---|
| `DOMAIN_ERROR` | 422 | Erreur métier générique (racine ; ne devrait pas remonter telle quelle). |
| `INVALID_INPUT` | 422 | Donnée fournie invalide (montant ≤ 0, identifiant mal formé, énumération inconnue…). |
| `CURRENCY_MISMATCH` | 422 | Opération entre deux devises différentes. `details`: `left`, `right`. |
| `INSUFFICIENT_FUNDS` | 422 | Solde disponible insuffisant. |
| `BALANCE_CAP_EXCEEDED` | 422 | Le crédit ferait dépasser le plafond de solde du palier KYC. `details`: `limit`, `current_balance`, `incoming`, `currency`. |
| `UNSUPPORTED_COUNTRY` | 422 | Pays non pris en charge par le référentiel. |

## Limites & KYC

| `code` | HTTP | Quand |
|---|---|---|
| `LIMIT_EXCEEDED` | 422 | Plafond par opération / jour / mois atteint. `details`: `window`, `limit`, `already_used`, `remaining`, `requested`, `currency`. |
| `KYC_REQUIRED` | 422 | Palier de vérification d'identité insuffisant. `details`: `min_tier`. |

## Numéros de téléphone

| `code` | HTTP | Quand |
|---|---|---|
| `PHONE_NUMBER_LIMIT_REACHED` | 422 | 5 numéros déjà rattachés au compte. |
| `PHONE_NUMBER_ALREADY_LINKED` | 409 | Ce numéro appartient déjà à un compte. |
| `CANNOT_REMOVE_LAST_PHONE_NUMBER` | 422 | On ne retire pas le dernier numéro d'un compte. |
| `CANNOT_REMOVE_PRIMARY_PHONE_NUMBER` | 422 | Définir un autre numéro principal d'abord. |
| `PHONE_NUMBER_NOT_FOUND` | 404 | Numéro absent de ce compte. |
| `PHONE_NUMBER_NOT_VERIFIED` | 422 | Numéro pas encore vérifié par OTP. |

## Comptes & portefeuilles

| `code` | HTTP | Quand |
|---|---|---|
| `INVALID_CREDENTIALS` | 401 | Numéro ou code secret (PIN) incorrect. |
| `INVALID_ACCOUNT_STATE` | 422 | Opération non permise dans l'état actuel du compte / de l'agrégat. |
| `USER_FROZEN` | 409 | Compte gelé (back-office / conformité). |
| `ACCOUNT_CLOSED` | 409 | Compte clôturé. |
| `WALLET_FROZEN` | 409 | Portefeuille gelé. |
| `WALLET_NOT_FOUND` | 404 | Portefeuille inexistant. |
| `RECIPIENT_NOT_FOUND` | 404 | Aucun compte Flash pour ce numéro destinataire. |
| `SELF_TRANSFER` | 422 | Envoi d'argent à soi-même. |
| `INVALID_RESERVATION` | 422 | Montant de réservation incohérent avec les fonds réservés. |
| `NOT_A_MERCHANT` | 404 | Le compte visé n'est pas un marchand. |
| `NOT_AN_AGENT` | 404 | Le compte visé n'est pas un agent. |

## Cash (dépôt / retrait agent)

| `code` | HTTP | Quand |
|---|---|---|
| `AGENT_FLOAT_TOO_LOW` | 422 | Liquidité de l'agent insuffisante pour l'opération. |
| `WITHDRAWAL_CODE_INVALID` | 422 | Code de retrait erroné. |
| `WITHDRAWAL_CODE_EXPIRED` | 422 | Code de retrait périmé. |

## Coffre

| `code` | HTTP | Quand |
|---|---|---|
| `POCKET_LOCKED` | 409 | Poche verrouillée jusqu'à sa date d'échéance. |
| `POCKET_NOT_EMPTY` | 409 | Suppression d'une poche non vide refusée. |

## Interopérabilité opérateurs

| `code` | HTTP | Quand |
|---|---|---|
| `OPERATOR_GATEWAY_REJECTED` | 422 | La passerelle opérateur a refusé l'opération (fonds relâchés). |
| `OPERATOR_TRANSFER_NOT_RESOLVABLE` | 409 | Le transfert opérateur n'est plus `PENDING` (déjà résolu). |

## API marchande publique

| `code` | HTTP | Quand |
|---|---|---|
| `MERCHANT_API_KEY_INVALID` | 401 | Clé d'API inconnue / révoquée, marchand suspendu ou KYB non validé. |

## Cartes virtuelles

| `code` | HTTP | Quand |
|---|---|---|
| `CARD_NOT_ACTIVE` | 409 | Carte gelée, expirée ou résiliée. |
| `CARD_LIMIT_REACHED` | 422 | Plafond jour / mois de la carte atteint. |
| `CHANNEL_DISABLED` | 409 | Canal (en ligne, sans contact, retrait, international) désactivé sur la carte. |

## Annulation / remboursement / idempotence

| `code` | HTTP | Quand |
|---|---|---|
| `REFUND_NOT_POSSIBLE` | 422 | Remboursement impossible (fonds du bénéficiaire déjà utilisés). |
| `REVERSAL_WINDOW_CLOSED` | 409 | Délai d'annulation de l'opération dépassé. |
| `DUPLICATE_OPERATION` | 409 | Clé d'idempotence déjà vue pour une autre requête ; l'opération n'est pas rejouée. |

## Authentification / OTP

| `code` | HTTP | Quand |
|---|---|---|
| `OTP_INVALID` | 422 | Code de vérification incorrect ou expiré. |
| `OTP_TOO_MANY_ATTEMPTS` | 429 | Trop d'essais sur ce code ; recommencer la demande d'OTP. |
