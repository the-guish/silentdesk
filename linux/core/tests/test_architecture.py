"""Keeps the layout honest: which layer may import which, and that every
abstract class has a concrete implementation. See silentdesk/apps/__init__.py."""

from __future__ import annotations

import ast
import asyncio
import importlib
import inspect
import sys
from pathlib import Path

import pytest

import silentdesk
from silentdesk import api, contract
from silentdesk.infra.settings import Settings

PACKAGE = Path(silentdesk.__file__).parent

# What each layer may import from inside silentdesk. Layers inside an app may
# only import from the same app.
ALLOWED = {
    "contract": {"contract"},
    "infra": {"infra"},
    "core": {"contract", "core"},
    "ports": {"contract", "core", "ports"},
    "application": {"contract", "core", "ports", "application"},
    "adapters": {"contract", "core", "ports", "adapters", "infra"},
    "wiring": {"contract", "core", "ports", "application", "adapters", "infra"},
    "apps": set(),
}
# Layers that may import only the standard library from outside silentdesk.
STDLIB_ONLY = {"contract", "core", "ports", "application"}
APP_LAYERS = {"core", "ports", "application", "adapters"}


def module_name(path: Path) -> str:
    parts = path.relative_to(PACKAGE.parent).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def layer(module: str) -> tuple[str, str | None]:
    """The layer a silentdesk module belongs to, and its app if it is in one."""
    parts = module.split(".")[1:]
    if not parts:
        return "top", None
    if parts[0] in ("contract", "infra"):
        return parts[0], None
    if parts[0] == "apps":
        if len(parts) == 1:
            return "apps", None
        if len(parts) == 2:
            return "wiring", parts[1]
        if parts[2] in APP_LAYERS:
            return parts[2], parts[1]
        return "wiring", parts[1]
    return "top", None


def imports(path: Path) -> list[str]:
    """Every module `path` imports, with relative imports made absolute."""
    module = module_name(path)
    package = module if path.name == "__init__.py" else module.rpartition(".")[0]
    found = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = ".".join(package.split(".")[: len(package.split(".")) - node.level + 1])
                found.append(f"{base}.{node.module}" if node.module else base)
            else:
                found.append(node.module or "")
    return found


SOURCES = sorted(PACKAGE.rglob("*.py"))


@pytest.mark.parametrize("path", SOURCES, ids=lambda path: str(path.relative_to(PACKAGE)))
def test_layers_import_only_what_they_may(path: Path):
    importer, app = layer(module_name(path))
    if importer == "top":
        return
    for target in imports(path):
        root = target.split(".")[0]
        if root == "__future__":
            continue
        if root != "silentdesk":
            if importer in STDLIB_ONLY:
                assert root in sys.stdlib_module_names, f"{importer} may only use the standard library: {target}"
            continue
        imported, imported_app = layer(target)
        assert imported in ALLOWED[importer], f"{importer} may not import {imported}: {target}"
        if imported_app is not None:
            assert imported_app == app, f"apps meet only through silentdesk.contract: {target}"


def all_classes() -> list[type]:
    classes = []
    # __main__ runs the CLI when imported.
    for path in (path for path in SOURCES if path.name != "__main__.py"):
        module = importlib.import_module(module_name(path))
        classes += [c for _, c in inspect.getmembers(module, inspect.isclass) if c.__module__ == module.__name__]
    return classes


def test_every_contract_and_port_has_a_concrete_implementation():
    classes = all_classes()
    abstract = [c for c in classes if inspect.isabstract(c) and layer(c.__module__)[0] in ("contract", "ports")]
    assert abstract, "found no abstract classes"
    for interface in abstract:
        assert any(issubclass(c, interface) and not inspect.isabstract(c) for c in classes), (
            f"{interface.__module__}.{interface.__name__} has no concrete implementation"
        )


def test_adapters_and_applications_are_concrete():
    for c in all_classes():
        if layer(c.__module__)[0] in ("adapters", "application"):
            assert not inspect.isabstract(c), f"{c.__module__}.{c.__name__} leaves abstract methods unimplemented"


def test_the_desk_is_wired_but_not_built_yet(tmp_path):
    desk = api.desk(Settings(data_dir=tmp_path))
    assert isinstance(desk, contract.Desk)
    assert sorted(desk.sources) == ["gmail", "tasks"]
    with pytest.raises(NotImplementedError):
        asyncio.run(desk.topics())
