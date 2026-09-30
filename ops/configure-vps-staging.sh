#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    printf '%s\n' 'uso: configure-vps-staging.sh <dominio>' >&2
    exit 2
fi

if [ "$(id -u)" -ne 0 ]; then
    printf '%s\n' 'execute com sudo para proteger os arquivos de ambiente' >&2
    exit 2
fi

site_host=$1
case "$site_host" in
    *[!A-Za-z0-9.-]* | .* | *..* | *.)
        printf '%s\n' 'dominio invalido' >&2
        exit 2
        ;;
esac

for command_name in docker openssl; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'comando obrigatorio ausente: %s\n' "$command_name" >&2
        exit 1
    fi
done

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_dir/.." && pwd)

if [ ! -f "$project_root/compose.production.yml" ]; then
    printf '%s\n' 'compose.production.yml ausente' >&2
    exit 1
fi

for image_name in \
    partner-reports:staging \
    partner-reports-backup:staging \
    caddy:2-alpine \
    postgres:17-alpine; do
    if ! docker image inspect "$image_name" >/dev/null 2>&1; then
        printf 'imagem obrigatoria ausente: %s\n' "$image_name" >&2
        exit 1
    fi
done

caddy_image=$(docker image inspect caddy:2-alpine --format '{{index .RepoDigests 0}}')
postgres_image=$(docker image inspect postgres:17-alpine --format '{{index .RepoDigests 0}}')

case "$caddy_image:$postgres_image" in
    *'@sha256:'*'@sha256:'*) ;;
    *)
        printf '%s\n' 'digest oficial ausente para Caddy ou PostgreSQL' >&2
        exit 1
        ;;
esac

production_env=$project_root/deploy/production.env
compose_env=$project_root/deploy/compose.env
restic_env=$project_root/deploy/restic.env

if [ -e "$production_env" ] || [ -e "$compose_env" ] || [ -e "$restic_env" ]; then
    printf '%s\n' 'configuracao existente; recusa sobrescrever' >&2
    exit 1
fi

printf '%s' 'E-mail operacional para o certificado TLS: '
IFS= read -r acme_email
case "$acme_email" in
    *@*.*) ;;
    *)
        printf '%s\n' 'e-mail invalido' >&2
        exit 2
        ;;
esac

database_password=$(openssl rand -hex 32)
umask 077
install -d -m 700 "$project_root/secrets/restic"

production_tmp=$(mktemp "$project_root/deploy/.production.env.XXXXXX")
compose_tmp=$(mktemp "$project_root/deploy/.compose.env.XXXXXX")
restic_tmp=$(mktemp "$project_root/deploy/.restic.env.XXXXXX")
cleanup() {
    rm -f "$production_tmp" "$compose_tmp" "$restic_tmp"
}
trap cleanup EXIT HUP INT TERM

printf '%s\n' \
    'APP_ENV=staging' \
    "DATABASE_URL=postgresql+psycopg://partner_reports:$database_password@postgres:5432/partner_reports" \
    'POSTGRES_DB=partner_reports' \
    'POSTGRES_USER=partner_reports' \
    "POSTGRES_PASSWORD=$database_password" \
    'LOG_LEVEL=INFO' \
    'PDF_STORAGE_ROOT=/data/sources' \
    'REPORT_STORAGE_ROOT=/data/reports' \
    'PDF_FOUR_EYES=false' \
    'PDF_SYNTHETIC_CORRECTIONS=true' \
    'PDF_DATA_SCOPE=synthetic_only' \
    "SITE_ADDRESS=https://$site_host" \
    "ACME_EMAIL=$acme_email" \
    'PGHOST=postgres' \
    'PGPORT=5432' \
    'PGDATABASE=partner_reports' \
    'PGUSER=partner_reports' \
    "PGPASSWORD=$database_password" \
    >"$production_tmp"

printf '%s\n' \
    'APP_IMAGE=partner-reports:staging' \
    'BACKUP_IMAGE=partner-reports-backup:staging' \
    "CADDY_IMAGE=$caddy_image" \
    "POSTGRES_IMAGE=$postgres_image" \
    "PARTNER_REPORTS_ENV_FILE=$production_env" \
    "RESTIC_ENV_FILE=$restic_env" \
    "RESTIC_CONFIG_DIR=$project_root/secrets/restic" \
    >"$compose_tmp"

printf '%s\n' \
    'RESTIC_REPOSITORY=UNCONFIGURED' \
    'RESTIC_PASSWORD_FILE=/run/restic/password' \
    >"$restic_tmp"

chmod 600 "$production_tmp" "$compose_tmp" "$restic_tmp"
mv "$production_tmp" "$production_env"
mv "$compose_tmp" "$compose_env"
mv "$restic_tmp" "$restic_env"
trap - EXIT HUP INT TERM

printf '%s\n' \
    'configuration=created' \
    'production_env_mode=600' \
    'compose_env_mode=600' \
    'restic_env_mode=600' \
    'restic_destination=config_required'
