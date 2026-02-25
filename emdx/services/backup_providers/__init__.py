"""Backup provider implementations."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..backup_types import BackupProvider

PROVIDERS: dict[str, str] = {
    "google_drive": "emdx.services.backup_providers.google_drive:GoogleDriveProvider",
    "github": "emdx.services.backup_providers.github:GitHubProvider",
}


def get_provider(name: str) -> BackupProvider:
    """Get a backup provider instance by name.

    Raises ValueError if the provider is not recognized.
    """
    if name not in PROVIDERS:
        available = ", ".join(sorted(PROVIDERS))
        raise ValueError(f"Unknown provider: {name}. Available: {available}")

    module_path, class_name = PROVIDERS[name].rsplit(":", 1)

    import importlib

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    return cls()  # type: ignore[no-any-return]
