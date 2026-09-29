"""A deliberately small JSON Schema validator — stdlib only.

The store's schemas (``schemas/*.schema.json``) are normative, but clauDNA ships
no third-party runtime dependencies, so they are checked with this subset
instead of ``jsonschema``. Supported keywords, and nothing else:

``type`` (string or list) · ``enum`` · ``const`` · ``required`` · ``properties``
· ``additionalProperties`` (bool or schema) · ``items`` · ``minimum`` ·
``minLength`` · ``pattern`` · ``$ref`` (local ``#/$defs/...`` only) · ``$defs``

An unsupported keyword in a schema raises, so a schema can never silently ask
for a check this module doesn't perform.
"""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"

_SUPPORTED = {
    "$schema", "$id", "$defs", "$ref", "title", "description",
    "type", "enum", "const", "required", "properties", "additionalProperties",
    "items", "minimum", "minLength", "pattern",
}
_TYPES = {
    "object": dict, "array": list, "string": str, "integer": int,
    "number": (int, float), "boolean": bool, "null": type(None),
}


class SchemaError(ValueError):
    """The schema itself uses something this validator does not support."""


@functools.cache
def load(name: str) -> dict:
    """Load ``schemas/<name>.schema.json`` (cached; callers must not mutate it)."""
    return json.loads((SCHEMA_DIR / f"{name}.schema.json").read_text(encoding="utf-8"))


def _is_type(value: object, name: str) -> bool:
    if name in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, _TYPES[name])


def validate(instance: object, schema: dict, *, root: dict | None = None, path: str = "$") -> list[str]:
    """Return every violation of ``schema`` by ``instance`` (empty list = valid)."""
    root = schema if root is None else root
    unknown = set(schema) - _SUPPORTED
    if unknown:
        raise SchemaError(f"unsupported schema keyword(s) at {path}: {sorted(unknown)}")

    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/$defs/"):
            raise SchemaError(f"only local $defs refs are supported, got {ref}")
        return validate(instance, root["$defs"][ref.removeprefix("#/$defs/")], root=root, path=path)

    errors: list[str] = []
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(instance, t) for t in types):
            return [f"{path}: expected {'|'.join(types)}"]
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: must be one of {schema['enum']}")
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: does not match {schema['pattern']}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: below minimum {schema['minimum']}")
    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required {key!r}")
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, value in instance.items():
            if key in props:
                errors.extend(validate(value, props[key], root=root, path=f"{path}.{key}"))
            elif extra is False:
                errors.append(f"{path}: unexpected property {key!r}")
            elif isinstance(extra, dict):
                errors.extend(validate(value, extra, root=root, path=f"{path}.{key}"))
    if isinstance(instance, list) and "items" in schema:
        for i, item in enumerate(instance):
            errors.extend(validate(item, schema["items"], root=root, path=f"{path}[{i}]"))
    return errors
