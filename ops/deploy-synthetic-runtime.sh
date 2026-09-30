#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    printf '%s\n' 'uso: deploy-synthetic-runtime.sh <release.tar.gz>' >&2
    exit 2
fi
if [ "$(id -u)" -ne 0 ]; then
    printf '%s\n' 'execute com sudo' >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
if [ "$project_root" != /opt/partner-reports ]; then
    printf '%s\n' 'diretorio de implantacao inesperado' >&2
    exit 1
fi

release_archive=$1
case "$release_archive" in
    /*) ;;
    *) release_archive=$(CDPATH= cd -- "$(dirname -- "$release_archive")" && pwd)/$(basename -- "$release_archive") ;;
esac
if [ ! -f "$release_archive" ]; then
    printf '%s\n' 'pacote de implantacao ausente' >&2
    exit 1
fi

for command_name in awk curl docker mktemp sha256sum systemctl tar; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'comando obrigatorio ausente: %s\n' "$command_name" >&2
        exit 1
    fi
done

compose_file=$project_root/compose.production.yml
compose_env=$project_root/deploy/compose.env
production_env=$project_root/deploy/production.env
timer_name=partner-reports-backup.timer
service_name=partner-reports-backup.service
for required_file in "$compose_file" "$compose_env" "$production_env"; do
    if [ ! -f "$required_file" ]; then
        printf '%s\n' 'configuracao ativa obrigatoria ausente' >&2
        exit 1
    fi
done

if systemctl is-active --quiet "$service_name"; then
    printf '%s\n' 'backup em execucao; aguarde a conclusao' >&2
    exit 1
fi
if ! systemctl is-active --quiet "$timer_name"; then
    printf '%s\n' 'timer de backup inativo; restaure-o antes da implantacao' >&2
    exit 1
fi

if tar -tzf "$release_archive" | awk '
    /^\// || /(^|\/)\.\.($|\/)/ || /^deploy\/(production|compose|restic)\.env$/ || /^secrets\// {
        invalid=1
    }
    END { exit invalid ? 0 : 1 }
'; then
    printf '%s\n' 'pacote contem caminho proibido' >&2
    exit 1
fi

release_id=$(date -u +%Y%m%dT%H%M%SZ)
releases_root=/opt/partner-reports-releases
install -d -m 700 "$releases_root"
work_dir=$(mktemp -d "$releases_root/.deploy.XXXXXX")
case "$work_dir" in
    "$releases_root"/.deploy.*) ;;
    *) printf '%s\n' 'diretorio temporario inseguro' >&2; exit 1 ;;
esac
candidate=$work_dir/candidate
rollback=$releases_root/rollback-$release_id
install -d -m 700 "$candidate" "$rollback"

timer_was_active=0
changed=0
completed=0
cleanup() {
    exit_code=$?
    trap - EXIT HUP INT TERM
    if [ "$completed" -ne 1 ] && [ "$changed" -eq 1 ]; then
        cp -p "$rollback/compose.env" "$compose_env"
        cp -p "$rollback/production.env" "$production_env"
        tar -xzf "$rollback/project-files.tar.gz" -C "$project_root"
        docker compose --env-file "$compose_env" -f "$compose_file" up -d app proxy >/dev/null 2>&1 || true
        printf '%s\n' 'deployment_status=rolled_back' >&2
    fi
    if [ "$timer_was_active" -eq 1 ]; then
        systemctl start "$timer_name" >/dev/null 2>&1 || true
    fi
    case "$work_dir" in
        "$releases_root"/.deploy.*) rm -rf -- "$work_dir" ;;
    esac
    exit "$exit_code"
}
trap cleanup EXIT HUP INT TERM

tar -xzf "$release_archive" -C "$candidate"
for required_file in \
    Dockerfile pyproject.toml alembic.ini compose.production.yml \
    src/partner_reports/config.py ops/deploy-synthetic-runtime.sh; do
    if [ ! -e "$candidate/$required_file" ]; then
        printf 'arquivo ausente no pacote: %s\n' "$required_file" >&2
        exit 1
    fi
done

new_image=partner-reports:synthetic-$release_id
docker build --target production --tag "$new_image" "$candidate"
docker run --rm --env-file "$production_env" \
    -e APP_ENV=production -e PDF_DATA_SCOPE=synthetic_only \
    "$new_image" python -c \
    'from partner_reports.config import get_settings; s=get_settings(); assert s.is_production and s.synthetic_validation_only; print("runtime_scope=verified")'

systemctl stop "$timer_name"
timer_was_active=1
if systemctl is-active --quiet "$service_name"; then
    printf '%s\n' 'backup iniciou durante a preparacao; implantacao cancelada' >&2
    exit 1
fi

cp -p "$compose_env" "$rollback/compose.env"
cp -p "$production_env" "$rollback/production.env"
rollback_manifest=$work_dir/rollback-files.list
for relative_path in \
    Dockerfile pyproject.toml README.md alembic.ini compose.production.yml compose.staging.yml \
    src migrations deploy/Caddyfile deploy/Caddyfile.staging deploy/production.env.example \
    deploy/restic.env.example deploy/systemd ops; do
    if [ -e "$project_root/$relative_path" ]; then
        printf '%s\n' "$relative_path" >>"$rollback_manifest"
    fi
done
if [ ! -s "$rollback_manifest" ]; then
    printf '%s\n' 'nenhum arquivo ativo encontrado para rollback' >&2
    exit 1
fi
tar -czf "$rollback/project-files.tar.gz" -C "$project_root" -T "$rollback_manifest"

rewrite_env() {
    source_file=$1
    key=$2
    value=$3
    target_file=$4
    awk -v key="$key" -v value="$value" '
        BEGIN { found=0 }
        index($0, key "=") == 1 { print key "=" value; found=1; next }
        { print }
        END { if (!found) print key "=" value }
    ' "$source_file" >"$target_file"
}

production_next=$work_dir/production.env
rewrite_env "$production_env" APP_ENV production "$production_next"
rewrite_env "$production_next" PDF_DATA_SCOPE synthetic_only "$production_next.scope"
install -m 600 "$production_next.scope" "$production_env"

compose_next=$work_dir/compose.env
rewrite_env "$compose_env" APP_IMAGE "$new_image" "$compose_next"
install -m 600 "$compose_next" "$compose_env"

tar -cf - -C "$candidate" . | tar -xf - -C "$project_root"
chmod 600 "$production_env" "$compose_env"
changed=1

docker compose --env-file "$compose_env" -f "$compose_file" config --quiet
docker compose --env-file "$compose_env" -f "$compose_file" \
    --profile operations run --rm migrate
docker compose --env-file "$compose_env" -f "$compose_file" up -d postgres app proxy

attempt=0
until docker compose --env-file "$compose_env" -f "$compose_file" \
    exec -T app python -c \
    'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2)' \
    >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
        printf '%s\n' 'healthcheck interno falhou' >&2
        exit 1
    fi
    sleep 2
done

site_address=$(awk -F= '$1 == "SITE_ADDRESS" {sub(/^[^=]*=/, ""); print; exit}' "$production_env")
case "$site_address" in
    https://*) ;;
    *) printf '%s\n' 'SITE_ADDRESS invalido' >&2; exit 1 ;;
esac
public_attempt=0
until curl --fail --silent --show-error --max-time 15 "$site_address/health" \
    >/dev/null 2>&1; do
    public_attempt=$((public_attempt + 1))
    if [ "$public_attempt" -ge 30 ]; then
        printf '%s\n' 'healthcheck publico nao ficou disponivel em 60 segundos' >&2
        exit 1
    fi
    sleep 2
done

docker compose --env-file "$compose_env" -f "$compose_file" exec -T app python -c \
    'from partner_reports.config import get_settings; s=get_settings(); assert s.is_production and s.synthetic_validation_only; print("deployed_scope=synthetic_only")'

completed=1
if [ "$timer_was_active" -eq 1 ]; then
    systemctl start "$timer_name"
    systemctl is-active --quiet "$timer_name"
    timer_was_active=0
fi

sha256sum "$release_archive" >"$rollback/release.sha256"
printf '%s\n' \
    'deployment_status=verified' \
    'app_environment=production' \
    'data_scope=synthetic_only' \
    'public_health=ok' \
    'backup_timer=active' \
    "rollback_directory=$rollback"
