# Tâches Design & marque (`DSN`)

Identité : nom **Flash**. Idée du logo : « l'argent qui court vite » — une pièce / un
billet stylisé en mouvement, traits de vitesse, ou un éclair intégrant un symbole
monétaire. Couleur principale : **rouge bordeaux**. Couleur d'accompagnement à définir
(piste : un doré / ambre chaud pour contraster le bordeaux, + neutres).

- [ ] **DSN-001** · Palette : bordeaux principal (ex. `#6B1E2E` famille, à figer),
  secondaire chaud (doré/ambre), neutres (fonds, textes), sémantiques (succès, alerte,
  danger, info) — versions claire et sombre, contrastes AA vérifiés.
- [ ] **DSN-002** · `design/tokens.json` : couleurs, typographie (famille, échelles),
  espacements, rayons, ombres, durées d'animation. Source unique consommée par web et
  mobile (script de génération CSS vars + Dart).
- [ ] **DSN-003** · Logo principal SVG (`design/logo/flash-logo.svg`) : « argent qui
  court » + éclair, version horizontale (logo + mot‑clé) et symbole seul.
- [ ] **DSN-004** · Déclinaisons logo : monochrome bordeaux, blanc (fond foncé), noir,
  favicon, versions petites tailles lisibles.
- [ ] **DSN-005** · Icônes d'application : `design/app-icon/` (1024², maskable Android,
  iOS), splash screen bordeaux.
- [ ] **DSN-006** · Iconographie fonctionnelle : jeu d'icônes cohérent (envoyer, payer,
  retirer, déposer, coffre, épargne, carte, agent) — SVG optimisés.
- [ ] **DSN-007** · Typographie : choix d'une police libre (ex. Inter / Plus Jakarta
  Sans) + fallback système, poids utilisés, fichiers auto‑hébergés (pas de CDN).
- [ ] **DSN-008** · Composants clés maquettés (Figma export ou specs) : carte de solde,
  ligne d'historique, écran d'envoi avec aperçu des frais, reçu, carte virtuelle.
- [ ] **DSN-009** · Modèle de reçu (image + PDF) aux couleurs Flash, avec QR de
  vérification, utilisé par web et mobile.
- [ ] **DSN-010** · Guide de marque court (`design/BRAND.md`) : usage du logo, marges de
  protection, couleurs, ton, exemples corrects/incorrects.
