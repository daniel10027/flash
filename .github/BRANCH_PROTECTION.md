# Protection de la branche `main` (INFRA-013)

GitHub ne versionne pas ces réglages : ils s'appliquent une fois via l'API ou
l'UI. Le script ci-dessous est idempotent.

## Règle voulue

- Pas de push direct sur `main` — tout passe par PR.
- CI verte obligatoire avant merge :
  - `backend-ci / lint-type-test`
  - `web-ci / lint-type-test`
  - `openapi-check / spec-in-sync`
  - `openapi-check / contract`
- 1 review approuvée (via `CODEOWNERS`), réapprobation si nouveaux commits.
- Branche à jour avec `main` avant merge (`strict`).
- Historique linéaire, conversations résolues.
- Règle appliquée aussi aux administrateurs.

## Application

```sh
# nécessite `gh auth login` avec les droits admin sur le dépôt
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)"

gh api -X PUT "repos/$REPO/branches/main/protection" \
  --input .github/branch-protection.json
```

Le corps est dans [`branch-protection.json`](branch-protection.json). Adapter la
liste `required_status_checks.contexts` si les noms de jobs changent.
