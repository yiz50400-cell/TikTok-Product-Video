from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


ROOT_FILES = ("pyproject.toml", "uv.lock")
ROOT_TREES = ("src",)
BUSINESS_SKILL_TREES = (
    ".codex/skills/setup-employee-environment",
    ".codex/skills/change-product-main-image",
    ".codex/skills/tiktok-product-video-editor",
    ".codex/skills/shop-order-report",
    ".codex/skills/operate-tiktok-ads",
)
EMPLOYEE_SCRIPTS = (
    "scripts/bootstrap-employee-workspace.ps1",
    "scripts/setup-employee-workspace.ps1",
    "scripts/doctor-employee-workspace.ps1",
    "scripts/write-employee-environment-receipt.ps1",
    "scripts/build-employee-release.ps1",
)
DOMAIN_FILES = ("pyproject.toml", "uv.lock")
DOMAIN_TREES = ("src",)
DOMAINS = ("tk_ad_agent", "tk_report_agent")
EMPLOYEE_ASSET_FILES = (
    "AGENTS.md",
    "README.md",
    "CAPABILITIES.md",
    "DEPLOYMENT.md",
    "VERSION",
    "config/capabilities.yaml",
    "config/employee.example.yaml",
)

_IGNORED_DIRECTORY_NAMES = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        ".venv",
    }
)
_SECRET_FILENAMES = frozenset(
    {
        "credentials.json",
        "cookies.json",
        "id_rsa",
        "id_ed25519",
        "secrets.json",
        "secrets.yaml",
        "secrets.yml",
        "service-account.json",
        "token.json",
    }
)
_SECRET_CONTENT_PATTERNS = (
    re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
_VERSION_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]+){2}(?:[-+][0-9A-Za-z.-]+)?")
_REPARSE_POINT = 0x400


class EmployeeReleaseError(ValueError):
    """Raised when an employee release cannot be built safely."""


@dataclass(frozen=True, slots=True)
class EmployeeReleaseReceipt:
    version: str
    unpacked_path: Path
    archive_path: Path
    manifest_path: Path
    manifest_sha256: str
    file_count: int


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError as error:
        raise EmployeeReleaseError(f"unable to inspect allowed path: {path}") from error
    return path.is_symlink() or bool(attributes & _REPARSE_POINT)


def _validate_source_file(path: Path) -> bytes:
    if _is_reparse_point(path):
        raise EmployeeReleaseError(f"link or reparse point is not allowed: {path}")
    if not path.is_file():
        raise EmployeeReleaseError(f"required release file is missing: {path}")
    lowered = path.name.lower()
    if lowered.startswith(".env") or lowered == "employee.local.yaml":
        raise EmployeeReleaseError(f"local secret file is not allowed: {path}")
    if lowered in _SECRET_FILENAMES:
        raise EmployeeReleaseError(f"credential-like filename is not allowed: {path}")
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise EmployeeReleaseError(f"unable to read allowed release file: {path}") from error
    if any(pattern.search(payload) for pattern in _SECRET_CONTENT_PATTERNS):
        raise EmployeeReleaseError(f"high-confidence secret content detected: {path}")
    return payload


def _ignored_tree_path(relative: Path) -> bool:
    for part in relative.parts:
        lowered = part.lower()
        if lowered in _IGNORED_DIRECTORY_NAMES:
            return True
        if lowered.endswith(".egg-info"):
            return True
    return relative.suffix.lower() == ".pyc"


def _copy_file(source: Path, destination_root: Path, relative: str) -> None:
    normalized = PurePosixPath(relative)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise EmployeeReleaseError("release destination must be a safe relative path")
    payload = _validate_source_file(source)
    destination = destination_root.joinpath(*normalized.parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)


def _copy_tree(source: Path, destination_root: Path, relative_root: str) -> None:
    if _is_reparse_point(source):
        raise EmployeeReleaseError(f"link or reparse point is not allowed: {source}")
    if not source.is_dir():
        raise EmployeeReleaseError(f"required release tree is missing: {source}")
    for candidate in sorted(source.rglob("*"), key=lambda item: item.as_posix()):
        relative = candidate.relative_to(source)
        if _is_reparse_point(candidate):
            raise EmployeeReleaseError(
                f"link or reparse point is not allowed: {candidate}"
            )
        if _ignored_tree_path(relative):
            continue
        if candidate.is_dir():
            continue
        destination = PurePosixPath(relative_root, *relative.parts).as_posix()
        _copy_file(candidate, destination_root, destination)


def _unique_release_paths(destination: Path, version: str) -> tuple[Path, Path]:
    base = f"TikTok-Shop-总运营-v{version}"
    position = 1
    while True:
        name = base if position == 1 else f"{base}-build-{position}"
        unpacked = destination / name
        archive = destination / f"{name}.zip"
        if not unpacked.exists() and not archive.exists():
            return unpacked, archive
        position += 1


def _manifest(unpacked: Path, version: str) -> tuple[bytes, int]:
    files: list[dict[str, object]] = []
    for path in sorted(unpacked.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_dir() or path.name == "release-manifest.json":
            continue
        payload = path.read_bytes()
        files.append(
            {
                "path": path.relative_to(unpacked).as_posix(),
                "sha256": _sha256(payload),
                "size": len(payload),
            }
        )
    document = {
        "files": files,
        "schema_version": 1,
        "workspace_version": version,
    }
    payload = (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    return payload, len(files)


def _write_deterministic_archive(unpacked: Path, archive: Path) -> None:
    with ZipFile(archive, "x", compression=ZIP_DEFLATED, compresslevel=9) as output:
        for path in sorted(unpacked.rglob("*"), key=lambda item: item.as_posix()):
            if path.is_dir():
                continue
            relative = path.relative_to(unpacked).as_posix()
            info = ZipInfo(f"{unpacked.name}/{relative}")
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = (0o100644 & 0xFFFF) << 16
            output.writestr(info, path.read_bytes())


def build_employee_release(
    workspace_root: Path,
    destination: Path,
    *,
    version: str,
) -> EmployeeReleaseReceipt:
    root = Path(workspace_root).resolve()
    output = Path(destination).resolve()
    if type(version) is not str or _VERSION_PATTERN.fullmatch(version) is None:
        raise EmployeeReleaseError("version must be a semantic version string")
    if _is_reparse_point(root) or not root.is_dir():
        raise EmployeeReleaseError("workspace root must be a real directory")
    if output.exists() and not output.is_dir():
        raise EmployeeReleaseError("release destination must be a directory")
    output.mkdir(parents=True, exist_ok=True)
    unpacked, archive = _unique_release_paths(output, version)
    unpacked.mkdir()

    for relative in ROOT_FILES:
        _copy_file(root / relative, unpacked, relative)
    for relative in ROOT_TREES:
        _copy_tree(root / relative, unpacked, relative)
    for relative in BUSINESS_SKILL_TREES:
        _copy_tree(root / relative, unpacked, relative)
    for relative in EMPLOYEE_SCRIPTS:
        _copy_file(root / relative, unpacked, relative)
    for domain in DOMAINS:
        domain_root = root / "domains" / domain
        for relative in DOMAIN_FILES:
            target = PurePosixPath("domains", domain, relative).as_posix()
            _copy_file(domain_root / relative, unpacked, target)
        for relative in DOMAIN_TREES:
            target = PurePosixPath("domains", domain, relative).as_posix()
            _copy_tree(domain_root / relative, unpacked, target)
    employee_assets = root / "employee_workspace"
    for relative in EMPLOYEE_ASSET_FILES:
        _copy_file(employee_assets / relative, unpacked, relative)
    for relative in ("data/input/.gitkeep", "data/output/.gitkeep", "outputs/.gitkeep"):
        destination_file = unpacked.joinpath(*PurePosixPath(relative).parts)
        destination_file.parent.mkdir(parents=True, exist_ok=True)
        destination_file.write_bytes(b"")

    manifest_payload, file_count = _manifest(unpacked, version)
    manifest_path = unpacked / "release-manifest.json"
    manifest_path.write_bytes(manifest_payload)
    _write_deterministic_archive(unpacked, archive)
    return EmployeeReleaseReceipt(
        version=version,
        unpacked_path=unpacked,
        archive_path=archive,
        manifest_path=manifest_path,
        manifest_sha256=_sha256(manifest_payload),
        file_count=file_count,
    )


__all__ = [
    "EmployeeReleaseError",
    "EmployeeReleaseReceipt",
    "build_employee_release",
]
