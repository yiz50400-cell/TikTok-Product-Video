from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from .catalog import CapabilityCatalogError
from .doctor import run_doctor
from .qa import add_verify_parser, handle_verify
from .video_compliance import add_video_compliance_parser, handle_video_compliance
from .voiceover import add_voiceover_parser, handle_voiceover


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tk-ops-workspace")
    subparsers = parser.add_subparsers(dest="command", required=True)
    doctor = subparsers.add_parser("doctor")
    doctor.add_argument("--workspace-root", type=Path, default=Path.cwd())
    doctor.add_argument("--config", type=Path, default=Path("config/employee.local.yaml"))
    add_video_compliance_parser(subparsers)
    add_voiceover_parser(subparsers)
    add_verify_parser(subparsers)
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
                employee_config_path=_doctor_config_path(workspace_root, namespace.config),
            )
        except CapabilityCatalogError:
            print(
                json.dumps(
                    {"error": "invalid_workspace", "performed_external_writes": False},
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 2
        print(json.dumps(report.to_public_dict(), ensure_ascii=False, sort_keys=True))
        return 0 if report.project_valid else 2
    if namespace.command == "video-compliance":
        return handle_video_compliance(namespace)
    if namespace.command == "verify":
        return handle_verify(namespace)
    if namespace.command == "voiceover":
        return handle_voiceover(namespace)
    return 2
