import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _service_block(compose: str, service: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(service)}:\n(?P<body>.*?)(?=^  [a-z][a-z0-9-]*:\n|\Z)",
        compose,
    )
    assert match is not None
    return match.group("body")


def test_restic_credentials_are_scoped_to_backup_services() -> None:
    compose = (ROOT / "compose.production.yml").read_text(encoding="utf-8")

    for service in (
        "app",
        "proxy",
        "migrate",
        "worker",
        "retention",
        "postgres",
        "restore-postgres",
    ):
        assert "RESTIC_ENV_FILE" not in _service_block(compose, service)

    for service in ("backup", "restore-test"):
        assert "${RESTIC_ENV_FILE:-./deploy/restic.env}" in _service_block(compose, service)

    production_example = (ROOT / "deploy" / "production.env.example").read_text(encoding="utf-8")
    restic_example = (ROOT / "deploy" / "restic.env.example").read_text(encoding="utf-8")
    assert "RESTIC_" not in production_example
    assert "RESTIC_REPOSITORY=" in restic_example
    assert "RESTIC_PASSWORD_FILE=" in restic_example
    assert "AWS_ACCESS_KEY_ID=" in restic_example
    assert "AWS_SECRET_ACCESS_KEY=" in restic_example
    assert "AWS_DEFAULT_REGION=auto" in restic_example


def test_forwarded_client_address_is_trusted_only_from_proxy_network() -> None:
    compose = (ROOT / "compose.production.yml").read_text(encoding="utf-8")
    subnet = "${INGRESS_SUBNET:-10.254.18.0/29}"

    proxy = _service_block(compose, "proxy")
    assert "networks: [edge, ingress]" in proxy
    assert "backend" not in proxy

    app = _service_block(compose, "app")
    assert "networks: [backend, ingress]" in app
    assert f"FORWARDED_ALLOW_IPS: {subnet}" in app

    for service in ("migrate", "worker", "retention", "postgres", "backup", "restore-test"):
        block = _service_block(compose, service)
        assert "ingress" not in block
        assert "FORWARDED_ALLOW_IPS" not in block

    ingress = re.search(r"(?ms)^  ingress:\n(?P<body>.*?)(?=^  [a-z]|\Z)", compose)
    assert ingress is not None
    assert "internal: true" in ingress.group("body")
    assert f"subnet: {subnet}" in ingress.group("body")
    assert "FORWARDED_ALLOW_IPS" not in (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_advbox_token_is_scoped_to_worker() -> None:
    compose = (ROOT / "compose.production.yml").read_text(encoding="utf-8")
    worker = _service_block(compose, "worker")
    assert "${ADVBOX_ENV_FILE:-./deploy/advbox.env}" in worker
    for service in (
        "app",
        "proxy",
        "migrate",
        "retention",
        "postgres",
        "backup",
        "restore-postgres",
        "restore-test",
    ):
        assert "ADVBOX_ENV_FILE" not in _service_block(compose, service)

    production_example = (ROOT / "deploy" / "production.env.example").read_text(encoding="utf-8")
    advbox_example = (ROOT / "deploy" / "advbox.env.example").read_text(encoding="utf-8")
    assert "ADVBOX_API_TOKEN" not in production_example
    assert "ADVBOX_API_TOKEN=" in advbox_example


def test_production_configuration_is_explicitly_synthetic_only() -> None:
    production_example = (ROOT / "deploy" / "production.env.example").read_text(encoding="utf-8")
    staging_configurator = (ROOT / "ops" / "configure-vps-staging.sh").read_text(encoding="utf-8")
    automation_cli = (ROOT / "src" / "partner_reports" / "jobs" / "automation_cli.py").read_text(
        encoding="utf-8"
    )

    assert "PDF_DATA_SCOPE=synthetic_only" in production_example
    assert "PDF_DATA_SCOPE=synthetic_only" in staging_configurator
    assert "settings.synthetic_validation_only" in automation_cli
    assert "settings.report_storage_root" in automation_cli


def test_synthetic_runtime_deployer_is_reversible_and_preserves_secrets() -> None:
    script = (ROOT / "ops" / "deploy-synthetic-runtime.sh").read_text(encoding="utf-8")

    assert "PDF_DATA_SCOPE synthetic_only" in script
    assert "APP_ENV production" in script
    assert "deployment_status=rolled_back" in script
    assert 'cp -p "$rollback/compose.env" "$compose_env"' in script
    assert 'cp -p "$rollback/production.env" "$production_env"' in script
    assert 'if [ -e "$project_root/$relative_path" ]' in script
    assert '-T "$rollback_manifest"' in script
    assert "production|compose|restic" in script
    assert "pacote contem caminho proibido" in script
    assert 'systemctl stop "$timer_name"' in script
    assert 'systemctl start "$timer_name"' in script
    assert "timer de backup inativo; restaure-o antes da implantacao" in script
    assert "--profile operations run --rm migrate" in script
    assert 'curl --fail --silent --show-error --max-time 15 "$site_address/health"' in script
    assert 'if [ "$public_attempt" -ge 30 ]' in script
    assert "healthcheck publico nao ficou disponivel em 60 segundos" in script
    assert "set -x" not in script


def test_release_builder_packages_only_explicit_runtime_paths() -> None:
    script = (ROOT / "ops" / "build-vps-release.ps1").read_text(encoding="utf-8")

    assert '"src"' in script
    assert '"migrations"' in script
    assert '"ops"' in script
    assert '"deploy/systemd"' in script
    assert '"deploy/production.env"' not in script
    assert '"deploy/restic.env"' not in script
    assert "Get-FileHash -Algorithm SHA256" in script


def test_restic_secret_file_is_excluded_from_git_and_build_context() -> None:
    for ignore_file in (".gitignore", ".dockerignore"):
        entries = {
            line.strip() for line in (ROOT / ignore_file).read_text(encoding="utf-8").splitlines()
        }
        assert "deploy/restic.env" in entries
        assert "deploy/advbox.env" in entries


def test_r2_configurator_does_not_echo_or_overwrite_secrets() -> None:
    script = (ROOT / "ops" / "configure-restic-r2.sh").read_text(encoding="utf-8")

    assert "stty -echo" in script
    assert "recusa sobrescrever" in script
    assert 'chmod 600 "$restic_tmp" "$password_tmp"' in script
    assert 'chown 10001:10001 "$restic_dir" "$password_file"' in script
    assert 'chmod 700 "$restic_dir"' in script
    assert 'chmod 600 "$password_file"' in script
    assert "docker compose" in script
    assert "config --quiet" in script
    assert "set -x" not in script
    assert "printf '%s\\n' \"$secret_access_key\"" not in script


def test_r2_account_repair_is_narrow_and_does_not_echo_identifier() -> None:
    script = (ROOT / "ops" / "update-restic-r2-account.sh").read_text(encoding="utf-8")

    assert "stty -echo" in script
    assert "RESTIC_REPOSITORY=s3:https://*.r2.cloudflarestorage.com/*" in script
    assert 'done <"$restic_env"' in script
    assert "config --quiet" in script
    assert "set -x" not in script


def test_r2_access_key_repair_validates_shape_and_rewrites_only_target() -> None:
    script = (ROOT / "ops" / "update-restic-r2-access-key.sh").read_text(encoding="utf-8")

    assert "stty -echo" in script
    assert '"${#access_key_id}" -ne 32' in script
    assert "AWS_ACCESS_KEY_ID=*)" in script
    assert 'done <"$restic_env"' in script
    assert "config --quiet" in script
    assert "set -x" not in script


def test_backup_timer_is_daily_persistent_and_uses_isolated_backup_profile() -> None:
    service = (ROOT / "deploy" / "systemd" / "partner-reports-backup.service").read_text(
        encoding="utf-8"
    )
    timer = (ROOT / "deploy" / "systemd" / "partner-reports-backup.timer").read_text(
        encoding="utf-8"
    )
    installer = (ROOT / "ops" / "install-backup-timer.sh").read_text(encoding="utf-8")

    assert "--profile backup run --rm backup" in service
    assert "deploy/restic.env" in service
    assert "OnCalendar=*-*-* 03:30:00 America/Sao_Paulo" in timer
    assert "RandomizedDelaySec=15m" in timer
    assert "Persistent=true" in timer
    assert "systemd-analyze verify" in installer
    assert "unidade existente divergente" in installer
    assert 'systemctl enable --now "$timer_name"' in installer


def test_r2_eu_migration_validates_before_switching_active_configuration() -> None:
    script = (ROOT / "ops" / "migrate-restic-r2-eu.sh").read_text(encoding="utf-8")

    assert ".eu.r2.cloudflarestorage.com/$bucket_name/restic" in script
    assert "stty -echo" in script
    assert 'systemctl stop "$timer_name"' in script
    assert 'systemctl is-active --quiet "$service_name"' in script
    assert 'systemctl is-active --quiet "$timer_name"' in script
    assert "--profile backup run --rm --entrypoint restic backup cat config" in script
    assert "--profile backup run --rm --entrypoint restic backup init" in script
    assert "--profile backup run --rm backup" in script
    assert '-p "$validation_project"' in script
    assert "--profile restore-test run --rm restore-test" in script
    assert "--profile restore-test down --volumes" in script

    restore_position = script.index("--profile restore-test run --rm restore-test")
    switch_position = script.rindex('mv -f "$password_next" "$password_file"')
    assert restore_position < switch_position
    assert script.index("backup cat config") < script.index("backup init")


def test_r2_eu_migration_keeps_old_remote_and_sanitizes_output() -> None:
    script = (ROOT / "ops" / "migrate-restic-r2-eu.sh").read_text(encoding="utf-8")

    assert 'cp -p "$restic_env" "$old_restic_env"' in script
    assert 'cp -p "$password_file" "$old_password"' in script
    assert 'if [ "$switched" -eq 1 ] && [ "$committed" -eq 0 ]' in script
    assert "restic forget" not in script
    assert "rclone delete" not in script
    assert "set -x" not in script
    assert "printf '%s\\n' \"$secret_access_key\"" not in script
    assert '>"$operation_log" 2>&1' in script
    assert "printf 'failure_code=%s\\n' \"$failure_code\"" in script
    assert "failure_code=unclassified_failure" in script
    assert 'cat "$operation_log"' not in script
