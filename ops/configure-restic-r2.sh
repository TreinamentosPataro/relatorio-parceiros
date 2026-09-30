#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    printf '%s\n' 'uso: configure-restic-r2.sh <bucket>' >&2
    exit 2
fi

if [ "$(id -u)" -ne 0 ]; then
    printf '%s\n' 'execute com sudo para proteger os arquivos de segredo' >&2
    exit 2
fi

bucket_name=$1
case "$bucket_name" in
    *[!a-z0-9-]* | -* | *- | '')
        printf '%s\n' 'bucket invalido' >&2
        exit 2
        ;;
esac
if [ "${#bucket_name}" -lt 3 ] || [ "${#bucket_name}" -gt 63 ]; then
    printf '%s\n' 'bucket invalido' >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
production_env=$project_root/deploy/production.env
compose_env=$project_root/deploy/compose.env
restic_env=$project_root/deploy/restic.env
restic_dir=$project_root/secrets/restic
password_file=$restic_dir/password

for required_file in "$production_env" "$compose_env" "$project_root/compose.production.yml"; do
    if [ ! -f "$required_file" ]; then
        printf '%s\n' 'configuracao base ausente' >&2
        exit 1
    fi
done
if [ -e "$restic_env" ] || [ -e "$password_file" ]; then
    printf '%s\n' 'configuracao Restic existente; recusa sobrescrever' >&2
    exit 1
fi

read_secret() {
    prompt=$1
    old_tty=$(stty -g </dev/tty)
    trap 'stty "$old_tty" </dev/tty; printf "\n" >&2; exit 130' HUP INT TERM
    printf '%s' "$prompt" >/dev/tty
    stty -echo </dev/tty
    if ! IFS= read -r secret_value </dev/tty; then
        stty "$old_tty" </dev/tty
        trap - HUP INT TERM
        printf '\n' >/dev/tty
        return 1
    fi
    stty "$old_tty" </dev/tty
    trap - HUP INT TERM
    printf '\n' >/dev/tty
    REPLY=$secret_value
}

read_secret 'R2 Account ID: '
account_id=$REPLY
read_secret 'R2 Access Key ID: '
access_key_id=$REPLY
read_secret 'R2 Secret Access Key: '
secret_access_key=$REPLY
read_secret 'Senha nova do repositorio Restic: '
restic_password=$REPLY
read_secret 'Repita a senha do repositorio Restic: '
restic_password_confirmation=$REPLY

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
if [ -z "$access_key_id" ] || [ -z "$secret_access_key" ] || [ -z "$restic_password" ]; then
    printf '%s\n' 'credencial vazia recusada' >&2
    exit 2
fi
if [ "$restic_password" != "$restic_password_confirmation" ]; then
    printf '%s\n' 'senhas Restic diferentes' >&2
    exit 2
fi

umask 077
install -d -m 700 "$restic_dir"
restic_tmp=$(mktemp "$project_root/deploy/.restic.env.XXXXXX")
password_tmp=$(mktemp "$restic_dir/.password.XXXXXX")
production_tmp=$(mktemp "$project_root/deploy/.production.env.XXXXXX")
compose_tmp=$(mktemp "$project_root/deploy/.compose.env.XXXXXX")
cleanup() {
    rm -f "$restic_tmp" "$password_tmp" "$production_tmp" "$compose_tmp"
}
trap cleanup EXIT HUP INT TERM

printf '%s\n' \
    "RESTIC_REPOSITORY=s3:https://$account_id.r2.cloudflarestorage.com/$bucket_name/restic" \
    'RESTIC_PASSWORD_FILE=/run/restic/password' \
    "AWS_ACCESS_KEY_ID=$access_key_id" \
    "AWS_SECRET_ACCESS_KEY=$secret_access_key" \
    'AWS_DEFAULT_REGION=auto' \
    >"$restic_tmp"
printf '%s\n' "$restic_password" >"$password_tmp"

awk '!/^RESTIC_REPOSITORY=/ && !/^RESTIC_PASSWORD_FILE=/' \
    "$production_env" >"$production_tmp"
awk '!/^RESTIC_ENV_FILE=/' "$compose_env" >"$compose_tmp"
printf 'RESTIC_ENV_FILE=%s\n' "$restic_env" >>"$compose_tmp"

chmod 600 "$restic_tmp" "$password_tmp" "$production_tmp" "$compose_tmp"

cd "$project_root"
PARTNER_REPORTS_ENV_FILE=$production_tmp \
RESTIC_ENV_FILE=$restic_tmp \
RESTIC_CONFIG_DIR=$restic_dir \
    docker compose --env-file "$compose_tmp" -f compose.production.yml config --quiet

mv "$restic_tmp" "$restic_env"
mv "$password_tmp" "$password_file"
mv "$production_tmp" "$production_env"
mv "$compose_tmp" "$compose_env"
chown 10001:10001 "$restic_dir" "$password_file"
chmod 700 "$restic_dir"
chmod 600 "$password_file"
trap - EXIT HUP INT TERM

printf '%s\n' \
    'restic_backend=r2' \
    'restic_configuration=created' \
    'restic_password_owner=10001:10001' \
    'secret_modes=600' \
    'compose_validation=passed' \
    'repository_initialization=pending'
