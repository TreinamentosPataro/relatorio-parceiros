"""Private object storage boundary for PDF sources."""

import os
import re
import tempfile
from pathlib import Path
from typing import Protocol

from partner_reports.config import AppEnvironment

_OBJECT_KEY = re.compile(r"pdf-source/[0-9a-f]{32}\.pdf")


class PdfStorageUnavailable(RuntimeError):
    """Raised without exposing a path, filename, payload, or infrastructure detail."""


class PrivatePdfStorage(Protocol):
    def put(self, object_key: str, content: bytes) -> None: ...

    def delete(self, object_key: str) -> None: ...


class LocalPrivatePdfStorage:
    """Atomic local storage allowed only in development and test."""

    def __init__(self, root: Path, environment: AppEnvironment):
        self._root = root.resolve()
        self._environment = environment

    def _target(self, object_key: str) -> Path:
        if not _OBJECT_KEY.fullmatch(object_key):
            raise PdfStorageUnavailable("chave de objeto inválida")
        target = (self._root / object_key).resolve()
        if self._root not in target.parents:
            raise PdfStorageUnavailable("chave de objeto inválida")
        return target

    def _require_local(self) -> None:
        if self._environment is AppEnvironment.PRODUCTION:
            raise PdfStorageUnavailable("storage local indisponível neste ambiente")

    def put(self, object_key: str, content: bytes) -> None:
        self._require_local()
        target = self._target(object_key)
        temporary: Path | None = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".pending-", suffix=".pdf", dir=target.parent
            )
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            if target.exists():
                raise PdfStorageUnavailable("objeto já existente")
            os.replace(temporary, target)
            temporary = None
        except PdfStorageUnavailable:
            raise
        except OSError as exc:
            raise PdfStorageUnavailable("falha no storage privado") from exc
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def delete(self, object_key: str) -> None:
        self._require_local()
        target = self._target(object_key)
        try:
            target.unlink(missing_ok=True)
        except OSError as exc:
            raise PdfStorageUnavailable("falha na limpeza do storage privado") from exc
