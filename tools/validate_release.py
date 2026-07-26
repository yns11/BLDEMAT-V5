#!/usr/bin/env python3
"""Contrôles statiques bloquants avant déploiement ou création d'une release."""

from __future__ import annotations

import argparse
import ast
import hashlib
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared" / "bl_core"
APPS = ["app_creation", "app_administration"]
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
URL = re.compile(r"https?://(?!schema\.org|docs\.databricks\.com)[^\s\"']+")


class UniqueKeyLoader(yaml.SafeLoader):
    """Chargeur YAML qui refuse les clés silencieusement écrasées."""


def _mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f"clé dupliquée {key!r}, ligne {key_node.start_mark.line + 1}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _mapping,
)


def fail(message: str, errors: list[str]) -> None:
    errors.append(message)


def validate_python(errors: list[str]) -> None:
    for path in sorted(ROOT.rglob("*.py")):
        if any(part.startswith(".") for part in path.relative_to(ROOT).parts):
            continue
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            fail(f"Syntaxe Python : {path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}", errors)


def validate_shared(errors: list[str]) -> None:
    shared_names = {path.name for path in SHARED.glob("*.py")}
    for app in APPS:
        target = ROOT / "src" / app / "bl_core"
        target_names = {path.name for path in target.glob("*.py")}
        if shared_names != target_names:
            fail(f"{app}: liste bl_core désynchronisée", errors)
            continue
        for name in shared_names:
            expected = hashlib.sha256((SHARED / name).read_bytes()).hexdigest()
            actual = hashlib.sha256((target / name).read_bytes()).hexdigest()
            if expected != actual:
                fail(f"{app}: bl_core/{name} désynchronisé", errors)


def validate_yaml(errors: list[str]) -> None:
    for path in [ROOT / "databricks.yml", *sorted((ROOT / "src").glob("*/app.yaml"))]:
        try:
            data = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
        except Exception as exc:
            fail(f"YAML invalide {path.relative_to(ROOT)} : {exc}", errors)
            continue
        if not isinstance(data, dict):
            fail(f"YAML vide ou invalide : {path.relative_to(ROOT)}", errors)


def validate_migrations(errors: list[str]) -> None:
    migrations = sorted((ROOT / "sql" / "migrations").glob("V*.sql"))
    expected = [f"V{index:03d}" for index in range(1, len(migrations) + 1)]
    actual = [path.name.split("__", 1)[0] for path in migrations]
    if actual != expected:
        fail(f"Séquence de migrations invalide : {actual}, attendu {expected}", errors)
    for path in migrations:
        text = path.read_text(encoding="utf-8")
        if "{{schema}}" not in text:
            fail(f"Migration sans placeholder de schéma : {path.name}", errors)


def validate_secrets(errors: list[str]) -> None:
    inspected = [
        ROOT / "databricks.yml",
        *sorted((ROOT / "src").glob("*/app.yaml")),
    ]
    for path in inspected:
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if EMAIL.search(line):
                fail(f"Email codé en dur : {path.relative_to(ROOT)}:{line_number}", errors)
            if URL.search(line) and "${" not in line:
                fail(f"URL externe codée en dur : {path.relative_to(ROOT)}:{line_number}", errors)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    errors: list[str] = []
    validate_python(errors)
    validate_shared(errors)
    validate_yaml(errors)
    validate_migrations(errors)
    validate_secrets(errors)
    if errors:
        print("\n".join(f"ERREUR - {error}" for error in errors), file=sys.stderr)
        return 1
    print("Release valide : Python, YAML, migrations, secrets et code partagé.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
