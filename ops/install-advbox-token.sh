#!/bin/sh
set -eu

# Installs the Advbox API token for the worker only. The token is read without echo,
# never passed as an argument and never printed; only its GET-only check is reported.

replace=0
case "$#:${1:-}" in
    0:) ;;
    1:--replace) replace=1 ;;
    *) printf '%s\n' 'uso: install-advbox-token.sh [--replace]' >&2; exit 2 ;;
esac
if [ "$(id -u)" -ne 0 ]; then
    printf '%s\n' 'execute com sudo' >&2
    exit 2
fi
if [ ! -t 0 ]; then
    printf '%s\n' 'execute em terminal interativo' >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
if [ "$project_root" != /opt/partner-reports ]; then
    printf '%s\n' 'diretorio de implantacao inesperado' >&2
    exit 1
fi
example=$project_root/deploy/advbox.env.example
target=$project_root/deploy/advbox.env
compose_env=$project_root/deploy/compose.env
compose_file=$project_root/compose.production.yml
for required_file in "$example" "$compose_env" "$compose_file"; do
    if [ ! -f "$required_file" ]; then
        printf '%s\n' 'arquivo obrigatorio ausente' >&2
        exit 1
    fi
done
if [ -e "$target" ] && [ "$replace" -ne 1 ]; then
    printf '%s\n' 'token ja instalado; use --replace para substituir' >&2
    exit 1
fi

umask 077
tmp=$(mktemp "$project_root/deploy/.advbox.XXXXXX")
previous=
installed=0
restore_echo() { stty echo 2>/dev/null || true; }
cleanup() {
    exit_code=$?
    trap - EXIT HUP INT TERM
    restore_echo
    rm -f -- "$tmp"
    if [ "$exit_code" -ne 0 ] && [ -n "$previous" ] && [ -f "$previous" ]; then
        mv -f -- "$previous" "$target"
        printf '%s\n' 'advbox_token=previous_restored' >&2
    elif [ "$exit_code" -ne 0 ] && [ "$installed" -eq 1 ]; then
        rm -f -- "$target"
        printf '%s\n' 'advbox_token=not_installed' >&2
    elif [ -n "$previous" ]; then
        rm -f -- "$previous"
    fi
    exit "$exit_code"
}
trap cleanup EXIT HUP INT TERM

printf '%s' 'Token da API Advbox (nao sera exibido): ' >&2
stty -echo
IFS= read -r token
restore_echo
printf '\n' >&2

case "$token" in
    '' | *[!A-Za-z0-9._~+/=-]*)
        printf '%s\n' 'token vazio ou com caracteres inesperados' >&2
        exit 1
        ;;
esac
if [ "${#token}" -lt 20 ] || [ "${#token}" -gt 1024 ]; then
    printf '%s\n' 'token com tamanho inesperado' >&2
    exit 1
fi

# ENVIRON keeps the token out of the process argument list visible to other users.
ADVBOX_TOKEN_INPUT=$token awk '
    index($0, "ADVBOX_API_TOKEN=") == 1 { print "ADVBOX_API_TOKEN=" ENVIRON["ADVBOX_TOKEN_INPUT"]; found=1; next }
    { print }
    END { if (!found) exit 1 }
' "$example" >"$tmp"
unset token

if [ -e "$target" ]; then
    previous=$project_root/deploy/.advbox.previous
    cp -p -- "$target" "$previous"
fi
chown root:root "$tmp"
chmod 600 "$tmp"
mv -f -- "$tmp" "$target"
installed=1

# Validate with one GET-only request from the worker container, the only token consumer.
check=$(docker compose --env-file "$compose_env" -f "$compose_file" --profile operations \
    run --rm --no-deps -T worker python -m partner_reports.jobs.automation_cli check-advbox \
    2>/dev/null | grep '^advbox_api=' || true)
if [ "$check" != advbox_api=ok ]; then
    printf '%s\n' "${check:-advbox_api=unverified}" >&2
    exit 1
fi

printf '%s\n' 'advbox_token=installed' 'advbox_api=ok'
