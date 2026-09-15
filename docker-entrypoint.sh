#!/bin/sh
# Single source of truth for "how this container starts," used identically
# by docker-compose locally and by any Dockerfile-based host in production
# (Railway, Render, Fly.io) — none of the latter read docker-compose.yml's
# command override, so it has to live here instead.
set -e

alembic upgrade head
exec gunicorn -w "${WEB_CONCURRENCY:-4}" -b "0.0.0.0:${PORT:-8000}" wsgi:app
