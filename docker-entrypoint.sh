#!/bin/sh
# Single source of truth for "how this container starts," used identically
# by docker-compose locally and by any Dockerfile-based host in production
# (Railway, Render, Fly.io) — none of the latter read docker-compose.yml's
# command override, so it has to live here instead.
set -e

alembic upgrade head
# gthread, not the default sync worker: GET /api/v1/solar/live holds its
# response open for as long as a dashboard is watching it, so one SSE viewer
# per sync worker would consume the entire pool — four open Solar tabs and
# the API stops answering anything else. Threads let a worker serve other
# requests while a stream is parked on its poll interval (the DB connection
# is released between polls; see services/solar_live.py).
exec gunicorn -w "${WEB_CONCURRENCY:-4}" -k gthread --threads "${WEB_THREADS:-4}" -b "0.0.0.0:${PORT:-8000}" wsgi:app
