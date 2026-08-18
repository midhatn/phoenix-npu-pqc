"""Compatibility entrypoint; prefer the extensionless ``py .\\install`` command."""

from __future__ import annotations

import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

INSTALL = Path(__file__).with_name("install")


def main() -> int:
    """Delegate legacy ``py .\\install.py`` calls to the current bootstrap."""
    loader = SourceFileLoader("phoenix_pqc_install_compat", str(INSTALL))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise RuntimeError(f"Unable to load extensionless bootstrap: {INSTALL}")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.entrypoint()


if __name__ == "__main__":
    raise SystemExit(main())
