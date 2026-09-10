// Génère src/shared/theme/tokens.css à partir de design/tokens.json (source partagée).
// Usage : npm run tokens
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const tokens = JSON.parse(readFileSync(resolve(here, '../../design/tokens.json'), 'utf8'));

const lines = [];
// Ignore les clés de documentation (`comment`, `$*`) et les valeurs non textuelles.
const usable = (k, v) => typeof v === 'string' && k !== 'comment' && !k.startsWith('$');
const push = (k, v) => {
  if (!usable(k.split('-').pop(), v)) return;
  lines.push(`  --${k}: ${v};`);
};

for (const [scale, val] of Object.entries(tokens.color)) {
  if (typeof val === 'string') push(`color-${scale}`, val);
  else for (const [step, hex] of Object.entries(val)) push(`color-${scale}-${step}`, hex);
}
for (const [k, v] of Object.entries(tokens.font.family)) push(`font-${k}`, v);
for (const [k, v] of Object.entries(tokens.font.size)) push(`text-${k}`, v);
for (const [k, v] of Object.entries(tokens.font.weight)) push(`weight-${k}`, v);
for (const [k, v] of Object.entries(tokens.font.lineHeight)) push(`leading-${k}`, v);
for (const [k, v] of Object.entries(tokens.space)) push(`space-${k}`, v);
for (const [k, v] of Object.entries(tokens.radius)) push(`radius-${k}`, v);
for (const [k, v] of Object.entries(tokens.shadow)) push(`shadow-${k}`, v);
for (const [k, v] of Object.entries(tokens.duration)) push(`duration-${k}`, v);
for (const [k, v] of Object.entries(tokens.z)) push(`z-${k}`, v);

const css = `/* Généré par scripts/build-tokens.mjs — ne pas éditer à la main. */
:root {
${lines.join('\n')}

  /* Rôles sémantiques — thème clair */
  --bg: var(--color-neutral-50);
  --bg-elevated: var(--color-neutral-0);
  --bg-sunken: var(--color-neutral-100);
  --fg: var(--color-neutral-900);
  --fg-muted: var(--color-neutral-500);
  --border: var(--color-neutral-200);
  --primary: var(--color-brand-500);
  --primary-hover: var(--color-brand-600);
  --primary-fg: var(--color-neutral-0);
  --focus-ring: var(--color-brand-400);
}

:root[data-theme='dark'],
:root[data-theme='system'] {
  color-scheme: light dark;
}

@media (prefers-color-scheme: dark) {
  :root[data-theme='system'] {
    --bg: var(--color-neutral-900);
    --bg-elevated: var(--color-neutral-800);
    --bg-sunken: #0f0f12;
    --fg: var(--color-neutral-50);
    --fg-muted: var(--color-neutral-400);
    --border: var(--color-neutral-700);
    --primary: var(--color-brand-300);
    --primary-hover: var(--color-brand-200);
    --primary-fg: var(--color-neutral-900);
    --focus-ring: var(--color-brand-300);
  }
}

:root[data-theme='dark'] {
  --bg: var(--color-neutral-900);
  --bg-elevated: var(--color-neutral-800);
  --bg-sunken: #0f0f12;
  --fg: var(--color-neutral-50);
  --fg-muted: var(--color-neutral-400);
  --border: var(--color-neutral-700);
  --primary: var(--color-brand-300);
  --primary-hover: var(--color-brand-200);
  --primary-fg: var(--color-neutral-900);
  --focus-ring: var(--color-brand-300);
}
`;

const out = resolve(here, '../src/shared/theme/tokens.css');
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, css);
console.log(`tokens.css écrit (${lines.length} variables)`);
