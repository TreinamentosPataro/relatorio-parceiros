"""Report object access; local synthetic preview only until private storage is approved."""

import hashlib
import os
import re
import uuid
from pathlib import Path

from partner_reports.config import AppEnvironment


class ArtifactUnavailable(Exception):
    """No authorized artifact backend is configured."""


class SyntheticArtifactStore:
    """Read fixed development fixtures, never arbitrary paths or production data."""

    def __init__(self, output_root: Path, app_env: AppEnvironment) -> None:
        self.output_root = output_root
        self.app_env = app_env

    def read(self, key: str, kind: str) -> bytes:
        if self.app_env not in (AppEnvironment.DEVELOPMENT, AppEnvironment.TEST):
            raise ArtifactUnavailable
        if key not in {"synthetic/zero", "synthetic/one", "synthetic/many"} and not re.fullmatch(
            r"synthetic/generated/[0-9a-f]{32}", key
        ):
            raise ArtifactUnavailable
        if kind not in {"html", "pdf"}:
            raise ArtifactUnavailable
        suffix = ".html" if kind == "html" else ".pdf"
        if key.startswith("synthetic/generated/"):
            path = self.output_root / kind / f"generated_{key.rsplit('/', 1)[1]}{suffix}"
        else:
            scenario = key.split("/")[1]
            path = self.output_root / kind / f"preview_{scenario}{suffix}"
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise ArtifactUnavailable from exc
        if kind == "html" and b"SYNTHETIC-" not in content:
            raise ArtifactUnavailable
        if kind == "pdf" and not content.startswith(b"%PDF"):
            raise ArtifactUnavailable
        return content

    def write_generated(self, html: bytes, pdf: bytes) -> tuple[str, str]:
        """Stage two local-only synthetic objects before a DB version is made visible."""

        if self.app_env not in (AppEnvironment.DEVELOPMENT, AppEnvironment.TEST):
            raise ArtifactUnavailable
        if b"SYNTHETIC-" not in html or not pdf.startswith(b"%PDF"):
            raise ArtifactUnavailable
        key = f"synthetic/generated/{uuid.uuid4().hex}"
        identifier = key.rsplit("/", 1)[1]
        written: list[Path] = []
        try:
            for kind, content, suffix in (("html", html, ".html"), ("pdf", pdf, ".pdf")):
                directory = self.output_root / kind
                directory.mkdir(parents=True, exist_ok=True)
                target = directory / f"generated_{identifier}{suffix}"
                temporary = directory / f".{identifier}{suffix}.tmp"
                written.append(temporary)
                temporary.write_bytes(content)
                os.replace(temporary, target)
                written.append(target)
        except OSError:
            for path in written:
                path.unlink(missing_ok=True)
            raise
        digest = hashlib.sha256(html + pdf).hexdigest()
        return key, digest

    def remove_generated(self, key: str) -> None:
        if self.app_env not in (
            AppEnvironment.DEVELOPMENT,
            AppEnvironment.TEST,
        ) or not re.fullmatch(r"synthetic/generated/[0-9a-f]{32}", key):
            raise ArtifactUnavailable
        identifier = key.rsplit("/", 1)[1]
        for kind, suffix in (("html", ".html"), ("pdf", ".pdf")):
            (self.output_root / kind / f"generated_{identifier}{suffix}").unlink(missing_ok=True)
