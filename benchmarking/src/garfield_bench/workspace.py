from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path


class WorkspaceError(RuntimeError):
    pass


CONTROL_RUNTIME_PATHS = (
    ".swamp/_extension_catalog.db",
    ".swamp/_extension_catalog.db-shm",
    ".swamp/_extension_catalog.db-wal",
    ".swamp/bundles",
    ".swamp/pulled-extensions",
    ".swamp/report-bundles",
)


def materialize_workspace(base: Path, fixture_patch: Path, destination: Path) -> str:
    if destination.exists():
        raise WorkspaceError(f"workspace already exists: {destination}")
    shutil.copytree(base, destination, ignore=shutil.ignore_patterns(".git", ".jj", ".swamp"))
    _git(destination, "init", "--quiet")
    _git(destination, "config", "user.name", "Garfield Benchmark")
    _git(destination, "config", "user.email", "garfield-bench@example.invalid")
    _git(destination, "add", ".")
    _git(destination, "commit", "--quiet", "-m", "ledgerlite immutable base")
    _git(destination, "apply", str(fixture_patch.resolve()))
    return tree_hash(destination)


def install_coordinator_skill(workspace: Path, agents_repo: Path, treatment: str) -> Path:
    source = agents_repo / "skills" / treatment
    if not source.is_dir():
        raise WorkspaceError(f"coordinator skill not found: {source}")
    destination = workspace / ".agents" / "skills" / treatment
    shutil.copytree(source, destination)
    exclude = workspace / ".git" / "info" / "exclude"
    with exclude.open("a", encoding="utf-8") as handle:
        handle.write(f"\n/.agents/skills/{treatment}/\n")
    return destination


def materialize_control_repo(source_repo: Path, ledgerlite: Path, destination: Path) -> Path:
    """Create fresh Swamp state from the treatment's source repository."""
    destination.mkdir(parents=True)
    for relative in (".swamp.yaml", "extensions", "models"):
        source = source_repo / relative
        target = destination / relative
        if source.is_dir():
            shutil.copytree(source, target)
        elif source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    for relative in CONTROL_RUNTIME_PATHS:
        source = source_repo / relative
        if not source.exists():
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)

    source_workflows = source_repo / "workflows"
    if source_workflows.is_dir():
        shutil.copytree(source_workflows, destination / "workflows")

    workflows = ledgerlite / "workflows"
    if not workflows.is_dir():
        raise WorkspaceError(f"validation workflow directory is missing: {workflows}")
    shutil.copytree(workflows, destination / "workflows", dirs_exist_ok=True)
    return destination


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    excluded_parts = {".git", ".jj", ".swamp", "__pycache__"}
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root)
        if any(part in excluded_parts for part in relative.parts):
            continue
        if relative.parts[:3] == (".agents", "skills", "garfield"):
            continue
        if relative.parts[:3] == (".agents", "skills", "swamp-garfield"):
            continue
        if path.is_symlink():
            digest.update(relative.as_posix().encode())
            digest.update(b"L")
            digest.update(os.readlink(path).encode())
        elif path.is_file():
            digest.update(relative.as_posix().encode())
            digest.update(b"F")
            digest.update(path.read_bytes())
            digest.update(str(path.stat().st_mode & 0o777).encode())
    return digest.hexdigest()


def final_patch(workspace: Path) -> str:
    _git(workspace, "add", "-N", ".")
    return _git(workspace, "diff", "--binary", "HEAD").stdout


def changed_files(workspace: Path) -> list[str]:
    output = _git(workspace, "status", "--porcelain=v1", "--untracked-files=all").stdout
    result: list[str] = []
    for line in output.splitlines():
        if not line:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        result.append(path)
    return sorted(result)


def _git(workspace: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=workspace,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise WorkspaceError(
            f"git {' '.join(arguments)} failed in {workspace}: {completed.stderr.strip()}"
        )
    return completed
