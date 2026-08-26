#!/bin/bash
# Runs once, on first initialisation of the postgres data directory.
#
# Two roles on purpose:
#   * POSTGRES_USER (owner)  - owns the schema, runs Alembic migrations, may DDL.
#   * APP_DB_USER   (app)    - the role the API connects as. It is deliberately NOT
#                              the table owner so that the REVOKE UPDATE/DELETE on
#                              audit_log applied by the migration actually bites
#                              (a table owner / superuser would bypass it).
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE "${APP_DB_USER}" WITH LOGIN PASSWORD '${APP_DB_PASSWORD}' NOSUPERUSER NOCREATEDB NOCREATEROLE;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL
    CREATE DATABASE "${TEST_DB_NAME}" OWNER "${POSTGRES_USER}";
EOSQL

for db in "$POSTGRES_DB" "$TEST_DB_NAME"; do
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL
        GRANT CONNECT ON DATABASE "${db}" TO "${APP_DB_USER}";
EOSQL
    psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<-EOSQL
        GRANT USAGE ON SCHEMA public TO "${APP_DB_USER}";
EOSQL
done

echo "app role ${APP_DB_USER} and test database ${TEST_DB_NAME} created"
