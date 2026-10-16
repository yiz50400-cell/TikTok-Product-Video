from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import yaml


class CapabilityCatalogError(ValueError):
    """Raised when the employee capability catalog is invalid."""


_LOCAL_REQUIREMENTS = frozenset(
    {"employee_config", "ffmpeg_toolchain", "ziniao_cli"}
)
_HOST_REQUIREMENTS = frozenset(
    {
        "image_provider",
        "tiktok_ads_mcp_read",
        "tiktok_ads_mcp_write",
    }
)
_CAPABILITY_FIELDS = frozenset(
    {
        "id",
        "display_name",
        "skill",
        "package_path",
        "local_requirements",
        "host_requirements",
        "writes_external_state",
        "unattended_mode",
    }
)


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    id: str
    display_name: str
    skill: str
    package_path: str
    local_requirements: tuple[str, ...]
    host_requirements: tuple[str, ...]
    writes_external_state: bool
    unattended_mode: str | None = None


def _mapping(value: object, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CapabilityCatalogError(f"{context} must be a mapping")
    return value


def _text(payload: Mapping[str, Any], field: str, *, context: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CapabilityCatalogError(f"{context}.{field} must be a non-empty string")
    return value.strip()


def _requirements(
    payload: Mapping[str, Any],
    field: str,
    *,
    allowed: frozenset[str],
    label: str,
    context: str,
) -> tuple[str, ...]:
    values = payload.get(field)
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise CapabilityCatalogError(f"{context}.{field} must be a string list")
    result = tuple(values)
    if len(set(result)) != len(result):
        raise CapabilityCatalogError(f"{context}.{field} contains duplicates")
    unknown = sorted(set(result) - allowed)
    if unknown:
        raise CapabilityCatalogError(f"unknown {label}: {', '.join(unknown)}")
    return result


def _safe_package_path(value: str, *, context: str) -> str:
    posix = PurePosixPath(value.replace("\\", "/"))
    windows = PureWindowsPath(value)
    if (
        not value
        or posix.is_absolute()
        or windows.is_absolute()
        or ".." in posix.parts
    ):
        raise CapabilityCatalogError(f"{context}.package_path must be a safe relative path")
    return posix.as_posix()


def _parse_capability(value: object, *, index: int) -> CapabilityDefinition:
    context = f"capabilities[{index}]"
    payload = _mapping(value, context=context)
    unknown = sorted(set(payload) - _CAPABILITY_FIELDS)
    if unknown:
        raise CapabilityCatalogError(f"{context} has unknown fields: {', '.join(unknown)}")
    writes_external_state = payload.get("writes_external_state")
    if not isinstance(writes_external_state, bool):
        raise CapabilityCatalogError(
            f"{context}.writes_external_state must be boolean"
        )
    unattended_mode = payload.get("unattended_mode")
    if unattended_mode is not None and unattended_mode != "disabled":
        raise CapabilityCatalogError(
            f"{context}.unattended_mode must be disabled when present"
        )
    package_path = _safe_package_path(
        _text(payload, "package_path", context=context),
        context=context,
    )
    return CapabilityDefinition(
        id=_text(payload, "id", context=context),
        display_name=_text(payload, "display_name", context=context),
        skill=_text(payload, "skill", context=context),
        package_path=package_path,
        local_requirements=_requirements(
            payload,
            "local_requirements",
            allowed=_LOCAL_REQUIREMENTS,
            label="local requirement",
            context=context,
        ),
        host_requirements=_requirements(
            payload,
            "host_requirements",
            allowed=_HOST_REQUIREMENTS,
            label="host requirement",
            context=context,
        ),
        writes_external_state=writes_external_state,
        unattended_mode=unattended_mode,
    )


def load_capability_catalog(path: Path) -> tuple[CapabilityDefinition, ...]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise CapabilityCatalogError(f"unable to read capability catalog: {path}") from error
    except yaml.YAMLError as error:
        raise CapabilityCatalogError("capability catalog is not valid YAML") from error
    payload = _mapping(raw, context="capability catalog")
    if set(payload) != {"schema_version", "capabilities"}:
        raise CapabilityCatalogError(
            "capability catalog fields must be schema_version and capabilities"
        )
    if payload.get("schema_version") != 1:
        raise CapabilityCatalogError("capability catalog schema_version must be 1")
    values = payload.get("capabilities")
    if not isinstance(values, list) or not values:
        raise CapabilityCatalogError("capabilities must be a non-empty list")
    catalog = tuple(
        _parse_capability(value, index=index)
        for index, value in enumerate(values)
    )
    ids = [item.id for item in catalog]
    skills = [item.skill for item in catalog]
    if len(set(ids)) != len(ids):
        raise CapabilityCatalogError("duplicate capability id")
    if len(set(skills)) != len(skills):
        raise CapabilityCatalogError("duplicate skill")
    return catalog
