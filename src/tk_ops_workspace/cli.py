from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .catalog import CapabilityCatalogError
from .doctor import run_doctor
from .jimeng_prompt import add_jimeng_prompt_parser, handle_jimeng_prompt
from .release import EmployeeReleaseError, build_employee_release
from .video_compliance import add_video_compliance_parser, handle_video_compliance


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tk-ops-workspace")
    subparsers = parser.add_subparsers(dest="command", required=True)
    doctor = subparsers.add_parser("doctor")
    doctor.add_argument(
        "--workspace-root",
        type=Path,
        default=Path.cwd(),
    )
    doctor.add_argument(
        "--config",
        type=Path,
        default=Path("config/employee.local.yaml"),
    )
    release = subparsers.add_parser("build-release")
    release.add_argument("--workspace-root", type=Path, default=Path.cwd())
    release.add_argument(
        "--destination",
        type=Path,
        default=Path("dist/employee-workspace"),
    )
    release.add_argument("--version")
    add_jimeng_prompt_parser(subparsers)
    add_video_compliance_parser(subparsers)
    return parser


def _doctor_config_path(workspace_root: Path, config_path: Path) -> Path:
    if config_path.is_absolute():
        return config_path
    return workspace_root / config_path


def main(argv: Sequence[str] | None = None) -> int:
    namespace = build_parser().parse_args(argv)
    if namespace.command == "doctor":
        workspace_root = namespace.workspace_root.resolve()
        try:
            report = run_doctor(
                workspace_root=workspace_root,
                employee_config_path=_doctor_config_path(
                    workspace_root,
                    namespace.config,
                ),
            )
        except CapabilityCatalogError:
            print(
                json.dumps(
                    {
                        "error": "invalid_workspace",
                        "performed_external_writes": False,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 2
        print(
            json.dumps(
                report.to_public_dict(),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0 if report.project_valid else 2
    if namespace.command == "build-release":
        workspace_root = namespace.workspace_root.resolve()
        destination = namespace.destination
        if not destination.is_absolute():
            destination = workspace_root / destination
        try:
            version = namespace.version or (
                workspace_root / "employee_workspace" / "VERSION"
            ).read_text(encoding="utf-8").strip()
            receipt = build_employee_release(
                workspace_root,
                destination,
                version=version,
            )
        except (EmployeeReleaseError, OSError):
            print(
                json.dumps(
                    {
                        "error": "release_build_failed",
                        "performed_external_writes": False,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 2
        print(
            json.dumps(
                {
                    "archive_path": str(receipt.archive_path),
                    "file_count": receipt.file_count,
                    "manifest_sha256": receipt.manifest_sha256,
                    "performed_external_writes": False,
                    "unpacked_path": str(receipt.unpacked_path),
                    "version": receipt.version,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    if namespace.command == "jimeng-prompt":
        return handle_jimeng_prompt(namespace)
    if namespace.command == "video-compliance":
        return handle_video_compliance(namespace)
    return 2
