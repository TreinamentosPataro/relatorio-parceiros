#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    printf '%s\n' 'uso: migrate-restic-r2-eu.sh <bucket-eu>' >&2
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

for command_name in docker systemctl mktemp grep stty; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'comando obrigatorio ausente: %s\n' "$command_name" >&2
        exit 1
    fi
done

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
production_env=$project_root/deploy/production.env
compose_env=$project_root/deploy/compose.env
restic_env=$project_root/deploy/restic.env
restic_dir=$project_root/secrets/restic
password_file=$restic_dir/password
compose_file=$project_root/compose.production.yml
timer_name=partner-reports-backup.timer
service_name=partner-reports-backup.service
validation_project=partner-reports-r2-eu-validation

for required_file in \
    "$production_env" \
    "$compose_env" \
    "$restic_env" \
    "$password_file" \
    "$compose_file"; do
    if [ ! -f "$required_file" ]; then
        printf '%s\n' 'configuracao base ou Restic atual ausente' >&2
        exit 1
    fi
done

if docker ps -a --quiet --filter "label=com.docker.compose.project=$validation_project" | grep -q . \
    || docker volume ls --quiet --filter "label=com.docker.compose.project=$validation_project" | grep -q . \
    || docker network ls --quiet --filter "label=com.docker.compose.project=$validation_project" | grep -q .; then
    printf '%s\n' 'ambiente isolado de validacao ja existe; revise-o antes de continuar' >&2
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
read_secret 'R2 EU Access Key ID: '
access_key_id=$REPLY
read_secret 'R2 EU Secret Access Key: '
secret_access_key=$REPLY
read_secret 'Senha nova do repositorio Restic EU: '
restic_password=$REPLY
read_secret 'Repita a senha nova do repositorio Restic EU: '
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
if [ "${#access_key_id}" -ne 32 ] || [ "${#secret_access_key}" -ne 64 ]; then
    printf '%s\n' 'credencial S3 R2 com formato invalido' >&2
    exit 2
fi
if [ -z "$restic_password" ]; then
    printf '%s\n' 'senha Restic vazia recusada' >&2
    exit 2
fi
if [ "$restic_password" != "$restic_password_confirmation" ]; then
    printf '%s\n' 'senhas Restic diferentes' >&2
    exit 2
fi

umask 077
restic_tmp=$(mktemp "$project_root/deploy/.restic-eu.env.XXXXXX")
secret_tmp=$(mktemp -d "$project_root/secrets/.restic-eu.XXXXXX")
password_tmp=$secret_tmp/password
operation_log=$(mktemp "$project_root/deploy/.restic-eu-operation.XXXXXX")
old_restic_env=$(mktemp "$project_root/deploy/.restic-env-previous.XXXXXX")
old_password=$(mktemp "$restic_dir/.password-previous.XXXXXX")
password_next=$restic_dir/.password-next.$$
restic_env_next=$project_root/deploy/.restic-env-next.$$
timer_was_active=0
validation_started=0
switched=0
committed=0

cleanup() {
    exit_code=$?
    trap - EXIT HUP INT TERM
    if [ "$validation_started" -eq 1 ]; then
        PARTNER_REPORTS_ENV_FILE="$production_env" \
        RESTIC_ENV_FILE="$restic_tmp" \
        RESTIC_CONFIG_DIR="$secret_tmp" \
            docker compose -p "$validation_project" --env-file "$compose_env" \
            -f "$compose_file" --profile restore-test down --volumes \
            >"$operation_log" 2>&1 || true
    fi
    if [ "$switched" -eq 1 ] && [ "$committed" -eq 0 ]; then
        install -m 600 "$old_restic_env" "$restic_env_next"
        mv -f "$restic_env_next" "$restic_env"
        install -m 600 "$old_password" "$password_next"
        chown 10001:10001 "$password_next"
        mv -f "$password_next" "$password_file"
    fi
    rm -f \
        "$restic_tmp" \
        "$password_tmp" \
        "$operation_log" \
        "$old_restic_env" \
        "$old_password" \
        "$password_next" \
        "$restic_env_next"
    rmdir "$secret_tmp" 2>/dev/null || true
    if [ "$timer_was_active" -eq 1 ]; then
        systemctl start "$timer_name" >/dev/null 2>&1 || true
    fi
    exit "$exit_code"
}
trap cleanup EXIT HUP INT TERM

report_failure_code() {
    if grep -Eqi 'repository.*already.*(exist|initiali)|config file already exists' "$operation_log"; then
        failure_code=repository_already_initialized
    elif grep -Eqi 'InvalidAccessKeyId|invalid access key' "$operation_log"; then
        failure_code=invalid_access_key
    elif grep -Eqi 'SignatureDoesNotMatch|signature.*(does not match|mismatch)' "$operation_log"; then
        failure_code=signature_mismatch
    elif grep -Eqi 'AccessDenied|permission denied|403 Forbidden' "$operation_log"; then
        failure_code=access_denied
    elif grep -Eqi 'NoSuchBucket|bucket.*(does not exist|not found)|404 Not Found' "$operation_log"; then
        failure_code=bucket_not_found
    elif grep -Eqi 'InvalidArgument|400 Bad Request' "$operation_log"; then
        failure_code=invalid_argument
    elif grep -Eqi 'tls|ssl|handshake|certificate' "$operation_log"; then
        failure_code=tls_failure
    elif grep -Eqi 'timeout|timed out|connection refused|no such host|network.*unreachable' "$operation_log"; then
        failure_code=network_failure
    elif grep -Eqi '401 Unauthorized' "$operation_log"; then
        failure_code=unauthorized
    elif grep -Eqi '5[0-9][0-9] (Internal Server Error|Bad Gateway|Service Unavailable|Gateway Timeout)' "$operation_log"; then
        failure_code=remote_service_failure
    else
        failure_code=unclassified_failure
    fi
    printf 'failure_code=%s\n' "$failure_code" >&2
}

printf '%s\n' \
    "RESTIC_REPOSITORY=s3:https://$account_id.eu.r2.cloudflarestorage.com/$bucket_name/restic" \
    'RESTIC_PASSWORD_FILE=/run/restic/password' \
    "AWS_ACCESS_KEY_ID=$access_key_id" \
    "AWS_SECRET_ACCESS_KEY=$secret_access_key" \
    'AWS_DEFAULT_REGION=auto' \
    >"$restic_tmp"
printf '%s\n' "$restic_password" >"$password_tmp"
unset REPLY secret_value access_key_id secret_access_key restic_password restic_password_confirmation
chmod 600 "$restic_tmp" "$password_tmp" "$operation_log"
chmod 700 "$secret_tmp"
chown -R 10001:10001 "$secret_tmp"

cd "$project_root"
if ! PARTNER_REPORTS_ENV_FILE="$production_env" \
    RESTIC_ENV_FILE="$restic_tmp" \
    RESTIC_CONFIG_DIR="$secret_tmp" \
    docker compose --env-file "$compose_env" -f "$compose_file" config --quiet \
    >"$operation_log" 2>&1; then
    printf '%s\n' 'migration_status=failed stage=compose_validation' >&2
    exit 1
fi

if ! systemctl is-enabled --quiet "$timer_name" \
    || ! systemctl is-active --quiet "$timer_name"; then
    printf '%s\n' 'migration_status=failed stage=backup_timer_not_ready' >&2
    exit 1
fi
timer_was_active=1
systemctl stop "$timer_name"
if systemctl is-active --quiet "$service_name"; then
    printf '%s\n' 'migration_status=failed stage=backup_service_busy' >&2
    exit 1
fi

if PARTNER_REPORTS_ENV_FILE="$production_env" \
    RESTIC_ENV_FILE="$restic_tmp" \
    RESTIC_CONFIG_DIR="$secret_tmp" \
    docker compose --env-file "$compose_env" -f "$compose_file" \
    --profile backup run --rm --entrypoint restic backup cat config \
    >"$operation_log" 2>&1; then
    repository_state=existing
else
    if ! PARTNER_REPORTS_ENV_FILE="$production_env" \
        RESTIC_ENV_FILE="$restic_tmp" \
        RESTIC_CONFIG_DIR="$secret_tmp" \
        docker compose --env-file "$compose_env" -f "$compose_file" \
        --profile backup run --rm --entrypoint restic backup init \
        >"$operation_log" 2>&1; then
        printf '%s\n' 'migration_status=failed stage=repository_initialization' >&2
        report_failure_code
        exit 1
    fi
    repository_state=created
fi

if ! PARTNER_REPORTS_ENV_FILE="$production_env" \
    RESTIC_ENV_FILE="$restic_tmp" \
    RESTIC_CONFIG_DIR="$secret_tmp" \
    docker compose --env-file "$compose_env" -f "$compose_file" \
    --profile backup run --rm backup \
    >"$operation_log" 2>&1; then
    printf '%s\n' 'migration_status=failed stage=backup_verification' >&2
    report_failure_code
    exit 1
fi

validation_started=1
if ! PARTNER_REPORTS_ENV_FILE="$production_env" \
    RESTIC_ENV_FILE="$restic_tmp" \
    RESTIC_CONFIG_DIR="$secret_tmp" \
    docker compose -p "$validation_project" --env-file "$compose_env" \
    -f "$compose_file" --profile restore-test run --rm restore-test \
    >"$operation_log" 2>&1; then
    printf '%s\n' 'migration_status=failed stage=isolated_restore' >&2
    report_failure_code
    exit 1
fi
PARTNER_REPORTS_ENV_FILE="$production_env" \
RESTIC_ENV_FILE="$restic_tmp" \
RESTIC_CONFIG_DIR="$secret_tmp" \
    docker compose -p "$validation_project" --env-file "$compose_env" \
    -f "$compose_file" --profile restore-test down --volumes \
    >"$operation_log" 2>&1
validation_started=0

cp -p "$restic_env" "$old_restic_env"
cp -p "$password_file" "$old_password"
switched=1
install -m 600 "$password_tmp" "$password_next"
chown 10001:10001 "$password_next"
mv -f "$password_next" "$password_file"
install -m 600 "$restic_tmp" "$restic_env_next"
mv -f "$restic_env_next" "$restic_env"
chmod 700 "$restic_dir"

if [ "$timer_was_active" -eq 1 ]; then
    if ! systemctl start "$timer_name" \
        || ! systemctl is-active --quiet "$timer_name"; then
        printf '%s\n' 'migration_status=failed stage=timer_restart' >&2
        exit 1
    fi
    timer_was_active=0
fi
committed=1

printf '%s\n' \
    'r2_jurisdiction=eu' \
    "repository_state=$repository_state" \
    'repository_initialization=verified' \
    'backup_status=verified' \
    'restore_status=verified' \
    'active_configuration=updated' \
    'backup_timer=active'
