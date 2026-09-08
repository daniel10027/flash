# ADR 0003 — Ledger en partie double

**Statut :** accepté · **Date :** 2026-09-08

## Contexte
Une plateforme de monnaie électronique doit pouvoir prouver, à tout instant, où est
chaque unité de valeur : soldes clients, float des agents, dettes envers les marchands,
suspens opérateurs et carte, produits de frais. Un simple champ `balance` mutable ne le
permet pas et rend les incidents impossibles à auditer.

## Décision
- Toute variation de valeur passe par une **`LedgerTransaction`** composée de `Posting`
  (compte, sens débit/crédit, montant positif, wallet lié optionnel).
- Invariant strict : pour chaque devise d'une transaction, `Σ débits = Σ crédits`.
  Vérifié à la **construction** de l'objet (impossible d'instancier une transaction
  déséquilibrée).
- Les transactions sont **immuables**. Une erreur se corrige par une transaction
  `REVERSAL` qui référence l'originale. Aucune suppression, aucune modification.
- Plan de comptes (types) : `CLIENT_LIABILITY`, `FLASH_FEE_INCOME`, `AGENT_FLOAT`,
  `AGENT_COMMISSION_EXPENSE`, `OPERATOR_SUSPENSE`, `CARD_SCHEME_SUSPENSE`,
  `SAVINGS_LIABILITY`, `INTEREST_EXPENSE`, `BANK_SETTLEMENT`, `MERCHANT_PAYABLE`,
  `ROUNDING`.
- Le **solde d'un wallet** est une **projection** (`wallet_balances`) maintenue dans la
  **même transaction DB** que l'écriture ledger. Lecture rapide sans recomposer
  l'historique.
- Job de **réconciliation** (`reconcile_wallet_balances`) : recompute les soldes depuis
  les postings et alerte sur tout écart. Doit être à zéro.
- **Idempotence** obligatoire en amont : une `Idempotency-Key` déjà vue renvoie le
  résultat mémorisé sans réécrire.
- **Concurrence** : verrou pessimiste (`SELECT … FOR UPDATE`) sur les lignes de wallet
  impliquées, dans l'UoW, pour interdire deux débits concurrents passant le solde en
  négatif.

## Exemple — transfert de 10 000 XOF, frais 0,8 % = 80 XOF
```
DEBIT  CLIENT_LIABILITY (wallet émetteur)     10 080
CREDIT CLIENT_LIABILITY (wallet destinataire) 10 000
CREDIT FLASH_FEE_INCOME                            80
------------------------------------------------------
Σ débits = 10 080   Σ crédits = 10 080   ✓
```

## Conséquences
- Auditabilité totale, exports comptables directs (balance, journal).
- Plus de code et de rigueur sur chaque cas d'usage monétaire. Assumé et outillé par les
  fabriques `LedgerTransaction.*` qui garantissent l'équilibre.
