# Flash — image du backend (API + jobs + CLI).
# Multi-stage : `build` installe le paquet dans un venv, `dev` ajoute le rechargement,
# `prod` produit une image slim qui tourne sous gunicorn en utilisateur non-root.

# ---------------------------------------------------------------- build
FROM python:3.14-slim AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq5 curl \
 && rm -rf /var/lib/apt/lists/* \
 && python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip

# Couche dépendances : ne dépend que de pyproject.toml (bon cache).
COPY backend/pyproject.toml ./pyproject.toml
COPY backend/src/flash/__init__.py ./src/flash/__init__.py
RUN pip install -e .

# Couche code.
COPY backend/src ./src
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
COPY backend/scripts ./scripts
RUN chmod +x ./scripts/*.sh

# ---------------------------------------------------------------- dev
FROM build AS dev
ENV FLASH_ENV=development
EXPOSE 8000
CMD ["/app/scripts/dev-entrypoint.sh"]

# ---------------------------------------------------------------- prod
FROM python:3.14-slim AS prod
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    FLASH_ENV=production

RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --create-home --uid 10001 flash

WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY --from=build /app/src ./src
COPY --from=build /app/alembic ./alembic
COPY --from=build /app/alembic.ini ./alembic.ini
COPY --from=build /app/scripts ./scripts

USER flash
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", \
     "flash.interface.wsgi:app"]
