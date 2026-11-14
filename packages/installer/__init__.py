"""安装器：Skill 安装/升级，支持备份、幂等、回滚与配置保留。

- 源目录：包含若干 `<skill>/SKILL.md` 的目录；
- 目标目录：默认 `~/.codex/skills`（可用 `AI_FILM_CODEX_HOME` / `CODEX_HOME` 覆盖）；
- 同名旧目录先整体移入备份目录，再复制新版本；
- `references/knowledge-base.json` / `knowledge-base.json` 在升级时保留原字节；
- 任意一步失败则回滚：删除已复制目录并恢复备份。
"""
from __future__ import annotations

import datetime
import os
import shutil
from pathlib import Path
from typing import Any, Callable

PRESERVED_FILES = ("references/knowledge-base.json", "knowledge-base.json")


class InstallerError(RuntimeError):
    """安装/升级/回滚失败时抛出。"""


def detect_codex_home() -> Path:
    override = os.environ.get("AI_FILM_CODEX_HOME") or os.environ.get("CODEX_HOME")
    return Path(override) if override else Path.home() / ".codex"


def _preserved_bytes(skill_dir: Path) -> dict[str, bytes]:
    found: dict[str, bytes] = {}
    for rel in PRESERVED_FILES:
        path = skill_dir / rel
        if path.is_file():
            found[rel] = path.read_bytes()
    return found


def _restore_preserved(skill_dir: Path, preserved: dict[str, bytes]) -> None:
    for rel, data in preserved.items():
        path = skill_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def plan_install(source: str | Path, target: str | Path | None = None) -> dict[str, Any]:
    source_dir = Path(source)
    if not source_dir.is_dir():
        raise InstallerError(f"源目录不存在: {source_dir}")
    skills = sorted(
        child for child in source_dir.iterdir()
        if child.is_dir() and (child / "SKILL.md").is_file()
    )
    if not skills:
        raise InstallerError(f"{source_dir}: 未找到含 SKILL.md 的 Skill 目录")
    target_dir = Path(target) if target is not None else detect_codex_home() / "skills"
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = target_dir.parent / f"skills-backup-{stamp}"
    return {
        "ok": True,
        "source": str(source_dir),
        "target": str(target_dir),
        "skills": [skill.name for skill in skills],
        "backup": str(backup_dir),
    }


def install_skills(source: str | Path, target: str | Path | None = None,
                   backup_root: str | Path | None = None, dry_run: bool = False,
                   copy_hook: Callable[[Path], None] | None = None) -> dict[str, Any]:
    """安装/升级 Skill 目录；返回安装报告。"""
    plan = plan_install(source, target)
    source_dir = Path(plan["source"])
    target_dir = Path(plan["target"])
    backup_dir = Path(backup_root) / Path(plan["backup"]).name if backup_root else Path(plan["backup"])
    skills = sorted(
        child for child in source_dir.iterdir()
        if child.is_dir() and (child / "SKILL.md").is_file()
    )
    if dry_run:
        plan.update({"dry_run": True, "backup": str(backup_dir)})
        return plan

    target_dir.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    installed: list[str] = []
    preserved: dict[str, dict[str, bytes]] = {}
    try:
        for skill in skills:
            dest = target_dir / skill.name
            if dest.exists() or dest.is_symlink():
                preserved[skill.name] = _preserved_bytes(dest) if dest.is_dir() else {}
                backup_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(dest), str(backup_dir / skill.name))
                moved.append(skill.name)
            if copy_hook is not None:
                copy_hook(skill)
            shutil.copytree(skill, dest)
            installed.append(skill.name)
            if skill.name in preserved:
                _restore_preserved(dest, preserved[skill.name])
    except Exception as exc:  # noqa: BLE001 - 需要捕获任意失败并回滚
        for name in installed:
            shutil.rmtree(target_dir / name, ignore_errors=True)
        for name in moved:
            source_backup = backup_dir / name
            destination = target_dir / name
            if source_backup.exists() and not destination.exists():
                target_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source_backup), str(destination))
        raise InstallerError(f"安装失败，已回滚: {exc}") from exc

    return {
        "ok": True,
        "source": str(source_dir),
        "target": str(target_dir),
        "skills": [skill.name for skill in skills],
        "installed": installed,
        "backed_up": moved,
        "preserved": sorted(preserved),
        "backup": str(backup_dir),
        "dry_run": False,
    }


class Installer:
    """兼容旧接口：安装器服务。"""

    def __init__(self, repo_root: str | None = None):
        self.repo_root = repo_root

    def health(self) -> dict[str, Any]:
        return {"service": "installer", "implemented": True, "target_iteration": "1b"}

    def install(self, source: str | Path, target: str | Path | None = None,
                **kwargs: Any) -> dict[str, Any]:
        return install_skills(source, target=target, **kwargs)
