#!/usr/bin/env bash
set -Eeuo pipefail

: "${GUTCARE_MIGRATOR_PASSWORD:?GUTCARE_MIGRATOR_PASSWORD is required}"
: "${GUTCARE_APP_PASSWORD:?GUTCARE_APP_PASSWORD is required}"
: "${GUTCARE_WORKER_PASSWORD:?GUTCARE_WORKER_PASSWORD is required}"
: "${GUTCARE_ANALYSIS_WORKER_PASSWORD:?GUTCARE_ANALYSIS_WORKER_PASSWORD is required}"
: "${GUTCARE_NOTIFICATION_WORKER_PASSWORD:?GUTCARE_NOTIFICATION_WORKER_PASSWORD is required}"
: "${GUTCARE_PRIVACY_WORKER_PASSWORD:?GUTCARE_PRIVACY_WORKER_PASSWORD is required}"

# psql's \getenv keeps credentials out of command arguments and SQL logs.
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=ON_ERROR_STOP=1 --set=database_name="$POSTGRES_DB" <<'SQL'
\getenv migrator_password GUTCARE_MIGRATOR_PASSWORD
\getenv app_password GUTCARE_APP_PASSWORD
\getenv worker_password GUTCARE_WORKER_PASSWORD
\getenv analysis_worker_password GUTCARE_ANALYSIS_WORKER_PASSWORD
\getenv notification_worker_password GUTCARE_NOTIFICATION_WORKER_PASSWORD
\getenv privacy_worker_password GUTCARE_PRIVACY_WORKER_PASSWORD

CREATE ROLE gutcare_migrator LOGIN PASSWORD :'migrator_password';
CREATE ROLE gutcare_app LOGIN PASSWORD :'app_password';
CREATE ROLE gutcare_worker LOGIN PASSWORD :'worker_password';
CREATE ROLE gutcare_analysis_worker LOGIN PASSWORD :'analysis_worker_password';
CREATE ROLE gutcare_notification_worker LOGIN PASSWORD :'notification_worker_password';
CREATE ROLE gutcare_privacy_worker LOGIN PASSWORD :'privacy_worker_password';

GRANT CONNECT ON DATABASE :"database_name" TO gutcare_migrator, gutcare_app, gutcare_worker, gutcare_analysis_worker, gutcare_notification_worker, gutcare_privacy_worker;
GRANT CREATE ON DATABASE :"database_name" TO gutcare_migrator;
GRANT CREATE ON SCHEMA public TO gutcare_migrator;
SQL
