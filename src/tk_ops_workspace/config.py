from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from .models import EmployeeConfig, StoreBinding


class EmployeeConfigError(ValueError):
    """Raised when a local employee configuration is unsafe or ambiguous."""


_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "employee_id",
        "display_name",
        "stores",
    }
)
_STORE_FIELDS = frozenset(
    {
        "store_alias",
        "ziniao_store_id",
        "tiktok_shop_id",
        "advertiser_id",
        "authorization_profile_id",
        "timezone",
    }
)


def _require_mapping(value: object, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EmployeeConfigError(f"{context} must be a mapping")
    return value


def _reject_unknown_fields(
    payload: Mapping[str, Any],
    *,
    allowed: frozenset[str],
    context: str,
) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise EmployeeConfigError(f"{context} has unknown fields: {', '.join(unknown)}")


def _required_text(
    payload: Mapping[str, Any],
    field: str,
    *,
    context: str,
) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise EmployeeConfigError(f"{context}.{field} must be a non-empty string")
    normalized = value.strip()
    if normalized.casefold().startswith("replace-with-"):
        raise EmployeeConfigError(f"{context}.{field} still contains a placeholder")
    return normalized


def _parse_store(payload: object, *, index: int) -> StoreBinding:
    context = f"stores[{index}]"
    mapping = _require_mapping(payload, context=context)
    _reject_unknown_fields(mapping, allowed=_STORE_FIELDS, context=context)
    values = {
        field: _required_text(mapping, field, context=context)
        for field in _STORE_FIELDS
    }
    try:
        ZoneInfo(values["timezone"])
    except ZoneInfoNotFoundError as error:
        raise EmployeeConfigError(f"{context}.timezone is not a valid IANA timezone") from error
    return StoreBinding(**values)


def _assert_unique_stores(stores: tuple[StoreBinding, ...]) -> None:
    aliases: set[str] = set()
    ziniao_ids: set[str] = set()
    exact_scopes: set[tuple[str, str, str]] = set()
    for store in stores:
        alias_key = store.store_alias.casefold()
        if alias_key in aliases:
            raise EmployeeConfigError("duplicate store_alias")
        aliases.add(alias_key)

        if store.ziniao_store_id in ziniao_ids:
            raise EmployeeConfigError("duplicate ziniao_store_id")
        ziniao_ids.add(store.ziniao_store_id)

        if store.exact_scope in exact_scopes:
            raise EmployeeConfigError("duplicate exact store scope")
        exact_scopes.add(store.exact_scope)


def load_employee_config(path: Path) -> EmployeeConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise EmployeeConfigError(f"unable to read employee config: {path}") from error
    except yaml.YAMLError as error:
        raise EmployeeConfigError("employee config is not valid YAML") from error

    payload = _require_mapping(raw, context="employee config")
    _reject_unknown_fields(payload, allowed=_ROOT_FIELDS, context="employee config")
    if payload.get("schema_version") != 1:
        raise EmployeeConfigError("schema_version must be 1")

    employee_id = _required_text(payload, "employee_id", context="employee config")
    display_name = _required_text(payload, "display_name", context="employee config")
    store_values = payload.get("stores")
    if not isinstance(store_values, list) or not store_values:
        raise EmployeeConfigError("employee config must contain at least one store")
    stores = tuple(
        _parse_store(store_payload, index=index)
        for index, store_payload in enumerate(store_values)
    )
    _assert_unique_stores(stores)
    return EmployeeConfig(
        employee_id=employee_id,
        display_name=display_name,
        stores=stores,
    )
