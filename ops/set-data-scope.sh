#!/bin/sh
set -eu

# The only switch between synthetic validation and the private pilot with real data.
# Releases preserve whatever scope this script last verified.

if [ "$#" -ne 1 ]; then
    printf '%s\n' 'uso: set-data-scope.sh synthetic_only|private_pilot' >&2
    exit 2
fi
target_scope=$1
case "$target_scope" in
    synthetic_only | private_pilot) ;;
    *) printf '%s\n' 'escopo invalido' >&2; exit 2 ;;
esac
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
compose_file=$project_root/compose.production.yml
compose_env=$project_root/deploy/compose.env
production_env=$project_root/deploy/production.env
advbox_env=$project_root/deploy/advbox.env
worker_timer=partner-reports-worker.timer
worker_service=partner-reports-worker.service
backup_service=partner-reports-backup.service
for required_file in "$compose_file" "$compose_env" "$production_env"; do
    if [ ! -f "$required_file" ]; then
        printf '%s\n' 'configuracao ativa obrigatoria ausente' >&2
        exit 1
    fi
done

current_scope=$(awk -F= '$1 == "PDF_DATA_SCOPE" {sub(/^[^=]*=/, ""); print; exit}' "$production_env")
current_scope=${current_scope:-synthetic_only}
if [ "$current_scope" = "$target_scope" ]; then
    printf 'data_scope=%s\nscope_status=unchanged\n' "$target_scope"
    exit 0
fi

if [ "$target_scope" = private_pilot ]; then
    if [ ! -f "$advbox_env" ] || [ "$(stat -c %a "$advbox_env")" != 600 ]; then
        printf '%s\n' 'instale o token com ops/install-advbox-token.sh antes' >&2
        exit 1
    fi
    if [ ! -t 0 ]; then
        printf '%s\n' 'execute em terminal interativo' >&2
        exit 2
    fi
    printf '%s\n' \
        'O portal passara a aceitar PDFs e dados reais dos parceiros liberados.' \
        'Os parceiros de demonstracao deixarao de aparecer.' >&2
    printf '%s' 'Digite LIBERAR DADOS REAIS para confirmar: ' >&2
    IFS= read -r answer
    if [ "$answer" != 'LIBERAR DADOS REAIS' ]; then
        printf '%s\n' 'confirmacao recusada; nada foi alterado' >&2
        exit 1
    fi
fi

if systemctl is-active --quiet "$backup_service"; then
    printf '%s\n' 'backup em execucao; aguarde a conclusao' >&2
    exit 1
fi

compose() {
    docker compose --env-file "$compose_env" -f "$compose_file" "$@"
}
scope_check='import os; from partner_reports.config import get_settings; s=get_settings(); assert s.is_production and s.pdf_data_scope.value == os.environ["EXPECTED_SCOPE"]'

releases_root=/opt/partner-reports-releases
install -d -m 700 "$releases_root"
backup_dir=$releases_root/scope-$(date -u +%Y%m%dT%H%M%SZ)
install -d -m 700 "$backup_dir"
cp -p "$production_env" "$backup_dir/production.env"

worker_timer_was_active=0
changed=0
completed=0
cleanup() {
    exit_code=$?
    trap - EXIT HUP INT TERM
    if [ "$completed" -ne 1 ] && [ "$changed" -eq 1 ]; then
        cp -p "$backup_dir/production.env" "$production_env"
        compose up -d --force-recreate app >/dev/null 2>&1 || true
        printf 'scope_status=rolled_back\ndata_scope=%s\n' "$current_scope" >&2
    fi
    if [ "$worker_timer_was_active" -eq 1 ]; then
        systemctl start "$worker_timer" >/dev/null 2>&1 || true
    fi
    rm -f -- "$backup_dir/production.env.next"
    exit "$exit_code"
}
trap cleanup EXIT HUP INT TERM

# No job may run while the scope changes under it.
if systemctl is-active --quiet "$worker_timer"; then
    systemctl stop "$worker_timer"
    worker_timer_was_active=1
fi
if systemctl is-active --quiet "$worker_service"; then
    printf '%s\n' 'worker em execucao; tente novamente em alguns minutos' >&2
    exit 1
fi

# Rewrite the scope and drop the retired allowlist, which now fails closed if present.
awk -v scope="$target_scope" '
    index($0, "PDF_PILOT_PARTNER_IDS=") == 1 { next }
    index($0, "PDF_DATA_SCOPE=") == 1 { print "PDF_DATA_SCOPE=" scope; found=1; next }
    { print }
    END { if (!found) print "PDF_DATA_SCOPE=" scope }
' "$production_env" >"$backup_dir/production.env.next"

# Validate the new configuration in a throwaway container before touching the live app.
app_image=$(awk -F= '$1 == "APP_IMAGE" {sub(/^[^=]*=/, ""); print; exit}' "$compose_env")
if [ -z "$app_image" ]; then
    printf '%s\n' 'APP_IMAGE ausente' >&2
    exit 1
fi
docker run --rm --network none --env-file "$backup_dir/production.env.next" \
    -e EXPECTED_SCOPE="$target_scope" "$app_image" python -c "$scope_check"

install -m 600 "$backup_dir/production.env.next" "$production_env"
changed=1
compose up -d --force-recreate app

attempt=0
until compose exec -T app python -c \
    'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2)' \
    >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
        printf '%s\n' 'healthcheck interno falhou' >&2
        exit 1
    fi
    sleep 2
done
compose exec -T -e EXPECTED_SCOPE="$target_scope" app python -c "$scope_check"

completed=1
if [ "$worker_timer_was_active" -eq 1 ]; then
    systemctl start "$worker_timer"
    systemctl is-active --quiet "$worker_timer"
    worker_timer_was_active=0
fi

printf '%s\n' \
    "data_scope=$target_scope" \
    'scope_status=verified' \
    "previous_configuration=$backup_dir/production.env"
