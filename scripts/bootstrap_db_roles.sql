-- Cluster-level role bootstrap. Run once by an operator (or automatically
-- in local dev via docker-compose's initdb.d mount) with a superuser/owner
-- connection. Deliberately NOT part of the Alembic migration chain: role
-- creation is a cluster concern, often restricted on managed Postgres, and
-- shouldn't be re-run per-environment the way schema migrations are.
--
-- Why this file exists at all: Postgres row-level security is bypassed by
-- superusers and by the owner of the table (unless the table has FORCE ROW
-- LEVEL SECURITY, which this project's migration sets). Belt-and-suspenders:
-- the runtime app connects as a role that is neither the table owner nor a
-- superuser, so tenant isolation holds even if FORCE is ever accidentally
-- dropped from a future migration.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'solgrid_app') THEN
        CREATE ROLE solgrid_app LOGIN PASSWORD 'solgrid_app_password'
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE solgrid_tea TO solgrid_app;
GRANT USAGE ON SCHEMA public TO solgrid_app;

-- Table/sequence privileges for solgrid_app are granted at the end of the
-- initial Alembic migration (0001_initial_schema), once the tables that
-- need to be granted on actually exist. Default privileges below make sure
-- any table created later by a migration owner is auto-granted too, so
-- nobody has to remember a manual GRANT in every future migration.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO solgrid_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO solgrid_app;
