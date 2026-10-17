from __future__ import annotations

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .catalog import CapabilityDefinition, load_capability_catalog
from .config import EmployeeConfigError, load_employee_config
from .models import EmployeeConfig

CapabilityStatus = Literal[
    "available",
    "missing_config",
    "missing_local_dependency",
    "host_check_required",
    "invalid_project",
]


@dataclass(frozen=True, slots=True)
class CapabilityDiagnostic:
    capability_id: str
    display_name: str
    status: CapabilityStatus
    reasons: tuple[str, ...]
    host_requirements: tuple[str, ...]

    def to_public_dict(self) -> dict[str, object]:
        return {
            "id": self.capability_id,
            "display_name": self.display_name,
            "status": self.status,
            "reasons": list(self.reasons),
            "host_requirements": list(self.host_requirements),
        }


@dataclass(frozen=True, slots=True)
class DoctorReport:
    project_valid: bool
    capabilities: tuple[CapabilityDiagnostic, ...]
    store_aliases: tuple[str, ...]
    performed_external_writes: bool = False

    def to_public_dict(self) -> dict[str, object]:
        return {
            "project_valid": self.project_valid,
            "capabilities": [
                capability.to_public_dict()
                for capability in self.capabilities
            ],
            "store_aliases": list(self.store_aliases),
            "performed_external_writes": self.performed_external_writes,
        }


def _catalog_path(workspace_root: Path) -> Path:
    release_path = workspace_root / "config" / "capabilities.yaml"
    if release_path.is_file():
        return release_path
    return workspace_root / "employee_workspace" / "config" / "capabilities.yaml"


def _project_reasons(
    workspace_root: Path,
    capability: CapabilityDefinition,
) -> list[str]:
    reasons: list[str] = []
    if not (workspace_root / capability.package_path).is_dir():
        reasons.append("missing_package")
    skill_file = (
        workspace_root
        / ".codex"
        / "skills"
        / capability.skill
        / "SKILL.md"
    )
    if not skill_file.is_file():
        reasons.append("missing_skill")
    return reasons


def _load_optional_employee_config(
    path: Path,
) -> tuple[EmployeeConfig | None, bool]:
    if not path.is_file():
        return None, False
    try:
        return load_employee_config(path), False
    except EmployeeConfigError:
        return None, True


def _missing_local_dependency_reasons(
    capability: CapabilityDefinition,
    command_lookup: Callable[[str], str | None],
) -> list[str]:
    reasons: list[str] = []
    if (
        "ziniao_cli" in capability.local_requirements
        and command_lookup("ziniao-cli.CMD") is None
        and command_lookup("ziniao-cli") is None
    ):
        reasons.append("missing_ziniao_cli")
    if "ffmpeg_toolchain" in capability.local_requirements:
        if command_lookup("ffmpeg") is None:
            reasons.append("missing_ffmpeg")
        if command_lookup("ffprobe") is None:
            reasons.append("missing_ffprobe")
    return reasons


def _diagnose_capability(
    *,
    workspace_root: Path,
    capability: CapabilityDefinition,
    employee_config: EmployeeConfig | None,
    config_invalid: bool,
    command_lookup: Callable[[str], str | None],
) -> CapabilityDiagnostic:
    reasons = _project_reasons(workspace_root, capability)
    local_dependency_reasons: list[str] = []
    if reasons:
        status: CapabilityStatus = "invalid_project"
    elif "employee_config" in capability.local_requirements and config_invalid:
        status = "invalid_project"
        reasons.append("invalid_employee_config")
    elif "employee_config" in capability.local_requirements and employee_config is None:
        status = "missing_config"
        reasons.append("missing_employee_config")
    elif local_dependency_reasons := _missing_local_dependency_reasons(
        capability,
        command_lookup,
    ):
        status = "missing_local_dependency"
        reasons.extend(local_dependency_reasons)
    elif capability.host_requirements:
        status = "host_check_required"
        reasons.extend(capability.host_requirements)
    else:
        status = "available"
    return CapabilityDiagnostic(
        capability_id=capability.id,
        display_name=capability.display_name,
        status=status,
        reasons=tuple(reasons),
        host_requirements=capability.host_requirements,
    )


def run_doctor(
    *,
    workspace_root: Path,
    employee_config_path: Path,
    command_lookup: Callable[[str], str | None] = shutil.which,
) -> DoctorReport:
    root = workspace_root.resolve()
    catalog = load_capability_catalog(_catalog_path(root))
    employee_config, config_invalid = _load_optional_employee_config(
        employee_config_path.resolve()
    )
    capabilities = tuple(
        _diagnose_capability(
            workspace_root=root,
            capability=capability,
            employee_config=employee_config,
            config_invalid=config_invalid,
            command_lookup=command_lookup,
        )
        for capability in catalog
    )
    return DoctorReport(
        project_valid=all(
            capability.status != "invalid_project"
            for capability in capabilities
        ),
        capabilities=capabilities,
        store_aliases=(
            tuple(store.store_alias for store in employee_config.stores)
            if employee_config is not None
            else ()
        ),
    )
