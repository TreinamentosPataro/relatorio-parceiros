#!/bin/sh
set -eu

if [ "$#" -ne 0 ]; then
    printf '%s\n' 'uso: install-backup-timer.sh' >&2
    exit 2
fi
if [ "$(id -u)" -ne 0 ]; then
    printf '%s\n' 'execute com sudo' >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
service_name=partner-reports-backup.service
timer_name=partner-reports-backup.timer
source_dir=$project_root/deploy/systemd
target_dir=/etc/systemd/system

for command_name in docker systemctl systemd-analyze; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'comando obrigatorio ausente: %s\n' "$command_name" >&2
        exit 1
    fi
done
if [ "$(command -v docker)" != /usr/bin/docker ]; then
    printf '%s\n' 'docker fora do caminho esperado /usr/bin/docker' >&2
    exit 1
fi
for required_file in \
    "$source_dir/$service_name" \
    "$source_dir/$timer_name" \
    "$project_root/compose.production.yml" \
    "$project_root/deploy/compose.env" \
    "$project_root/deploy/restic.env"; do
    if [ ! -f "$required_file" ]; then
        printf '%s\n' 'arquivo obrigatorio ausente' >&2
        exit 1
    fi
done

for unit_name in "$service_name" "$timer_name"; do
    source_file=$source_dir/$unit_name
    target_file=$target_dir/$unit_name
    if [ -e "$target_file" ] && ! cmp -s "$source_file" "$target_file"; then
        printf 'unidade existente divergente: %s\n' "$unit_name" >&2
        exit 1
    fi
done

systemd-analyze verify "$source_dir/$service_name" "$source_dir/$timer_name"
systemd-analyze calendar '*-*-* 03:30:00 America/Sao_Paulo' >/dev/null

install -m 0644 "$source_dir/$service_name" "$target_dir/$service_name"
install -m 0644 "$source_dir/$timer_name" "$target_dir/$timer_name"
systemctl daemon-reload
systemctl enable --now "$timer_name" >/dev/null
systemctl is-enabled --quiet "$timer_name"
systemctl is-active --quiet "$timer_name"

next_run=$(systemctl show "$timer_name" --property=NextElapseUSecRealtime --value)
printf '%s\n' \
    'backup_timer=enabled' \
    'backup_timer=active' \
    'schedule=03:30_America_Sao_Paulo_randomized_15m' \
    "next_run=$next_run"
