# WEB-012 — image web multi-stage.
#   dev     : serveur Vite avec HMR (monté en volume par infra/docker-compose.yml).
#   build   : bundle de production.
#   runtime : service statique Caddy + config runtime injectée au démarrage.
# Contexte de build : ./web. Le client API typé (src/shared/api/schema.d.ts) est
# versionné ; régénérer avec `npm run gen:api` après une évolution de l'API.

FROM node:26-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:26-alpine AS dev
WORKDIR /app
ENV NODE_ENV=development
COPY --from=deps /app/node_modules ./node_modules
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

FROM node:26-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM caddy:2-alpine AS runtime
COPY --from=build /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
EXPOSE 80
ENV FLASH_API_BASE_URL="" \
    FLASH_ENV="production" \
    FLASH_SENTRY_DSN=""
HEALTHCHECK --interval=15s --timeout=3s CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
