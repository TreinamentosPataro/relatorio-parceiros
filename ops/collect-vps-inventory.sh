#!/bin/sh
set -eu

printf '%s\n' 'VPS inventory (safe technical fields)'
printf 'kernel='
uname -srm
printf 'architecture='
uname -m
printf 'cpu_count='
getconf _NPROCESSORS_ONLN
printf 'memory_kib='
awk '/^MemTotal:/ { print $2 }' /proc/meminfo
printf 'root_disk_kib_used_available='
df -Pk / | awk 'NR == 2 { print $2, $3, $4 }'

if command -v docker >/dev/null 2>&1; then
    printf 'docker='
    docker --version
    printf 'docker_compose='
    docker compose version
else
    printf '%s\n' 'docker=unavailable'
fi

if command -v ufw >/dev/null 2>&1; then
    printf '%s\n' 'firewall=ufw'
elif command -v nft >/dev/null 2>&1; then
    printf '%s\n' 'firewall=nftables'
else
    printf '%s\n' 'firewall=not_detected'
fi

if command -v timedatectl >/dev/null 2>&1; then
    printf 'time_sync='
    timedatectl show -p NTPSynchronized --value 2>/dev/null || printf '%s\n' 'unknown'
else
    printf '%s\n' 'time_sync=unknown'
fi
