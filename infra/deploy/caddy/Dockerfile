# Caddy de bord (TLS Let's Encrypt + reverse proxy) avec le module rate-limit.
FROM caddy:2.11-builder AS build
RUN xcaddy build \
    --with github.com/mholt/caddy-ratelimit

FROM caddy:2.11-alpine
COPY --from=build /usr/bin/caddy /usr/bin/caddy
COPY Caddyfile /etc/caddy/Caddyfile
HEALTHCHECK --interval=30s --timeout=5s \
  CMD wget -qO- http://127.0.0.1:2019/config/ >/dev/null || exit 1
