#!/bin/sh
set -eu

if [ "$#" -ne 0 ]; then
    printf '%s\n' 'uso: update-restic-r2-account.sh' >&2
    exit 2
fi
if [ "$(id -u)" -ne 0 ]; then
    printf '%s\n' 'execute com sudo' >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
restic_env=$project_root/deploy/restic.env
compose_env=$project_root/deploy/compose.env

if [ ! -f "$restic_env" ] || [ ! -f "$compose_env" ]; then
    printf '%s\n' 'configuracao Restic ausente' >&2
    exit 1
fi

old_tty=$(stty -g </dev/tty)
trap 'stty "$old_tty" </dev/tty; printf "\n" >&2; exit 130' HUP INT TERM
printf '%s' 'R2 Account ID correto: ' >/dev/tty
stty -echo </dev/tty
if ! IFS= read -r account_id </dev/tty; then
    stty "$old_tty" </dev/tty
    trap - HUP INT TERM
    printf '\n' >/dev/tty
    exit 1
fi
stty "$old_tty" </dev/tty
trap - HUP INT TERM
printf '\n' >/dev/tty

case "$account_id" in
    *[!a-fA-F0-9]* | '')
        printf '%s\n' 'account-id invalido' >&2
        exit 2
        ;;
esac
if [ "${#account_id}" -ne 32 ]; then
    printf '%s\n' 'account-id invalido' >&2
    exit 2
fi

umask 077
restic_tmp=$(mktemp "$project_root/deploy/.restic.env.XXXXXX")
cleanup() {
    rm -f "$restic_tmp"
}
trap cleanup EXIT HUP INT TERM

repository_found=false
while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
        RESTIC_REPOSITORY=s3:https://*.r2.cloudflarestorage.com/*)
            repository_path=${line#*.r2.cloudflarestorage.com}
            printf 'RESTIC_REPOSITORY=s3:https://%s.r2.cloudflarestorage.com%s\n' \
                "$account_id" "$repository_path" >>"$restic_tmp"
            repository_found=true
            ;;
        *) printf '%s\n' "$line" >>"$restic_tmp" ;;
    esac
done <"$restic_env"

if [ "$repository_found" != true ]; then
    printf '%s\n' 'endpoint R2 esperado ausente' >&2
    exit 1
fi

chmod 600 "$restic_tmp"
chown 0:0 "$restic_tmp"
cd "$project_root"
RESTIC_ENV_FILE=$restic_tmp \
    docker compose --env-file "$compose_env" -f compose.production.yml config --quiet
mv "$restic_tmp" "$restic_env"
trap - EXIT HUP INT TERM

printf '%s\n' \
    'r2_account_id=updated' \
    'restic_env_mode=600' \
    'compose_validation=passed' \
    'repository_initialization=pending'
