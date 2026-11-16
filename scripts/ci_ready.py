"""远端 CI 就绪检查（M26，零第三方依赖）。

检查 GitHub Actions 工作流是否包含预期的跨平台矩阵与关键步骤，并检查当前仓库
是否已配置 git remote（真实远端执行的前提）。

用法::

    python scripts/ci_ready.py                 # 本地自检（无 remote 仅提示，不失败）
    python scripts/ci_ready.py --require-remote  # 要求必须配置 remote（供 CI 使用）
    python scripts/ci_ready.py --json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = Path(".github") / "workflows" / "ci.yml"

REQUIRED_PHRASES = (
    "ubuntu-latest",
    "windows-latest",
    "macos-latest",
    '"3.11"',
    '"3.12"',
    "scripts/run_ci.py",
    "scripts/build_release.py",
    "scripts/package_smoke.py",
)
REQUIRED_SNIPPETS = ("strategy:", "matrix:", "upload-artifact")

REMOTE_HINT = (
    "配置远端后可真实执行矩阵：git remote add origin <仓库地址> && "
    "git push -u origin main，并在仓库 Settings → Actions 启用工作流（详见 docs/github-actions.md）"
)


def check_workflow(root: Path = REPO_ROOT) -> dict[str, object]:
    """检查工作流文件：存在性、矩阵与关键步骤短语。"""
    path = root / WORKFLOW
    if not path.is_file():
        return {
            "ok": False,
            "path": WORKFLOW.as_posix(),
            "missing": ["工作流文件不存在"],
            "hint": "创建 .github/workflows/ci.yml（参见 docs/github-actions.md）",
        }
    text = path.read_text(encoding="utf-8")
    missing = [phrase for phrase in REQUIRED_PHRASES if phrase not in text]
    missing.extend(snippet for snippet in REQUIRED_SNIPPETS if snippet not in text)
    return {
        "ok": not missing,
        "path": WORKFLOW.as_posix(),
        "missing": missing,
        "has_matrix": all(os_name in text for os_name in ("ubuntu-latest", "windows-latest", "macos-latest")),
        "hint": "" if not missing else "补齐工作流中的矩阵/步骤（详见 docs/github-actions.md）",
    }


def list_remotes(root: Path = REPO_ROOT) -> list[str]:
    """返回 git remote 名称列表（无 remote 或无 git 时返回空）。"""
    try:
        result = subprocess.run(
            ["git", "remote"],
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def check(root: Path = REPO_ROOT, *, require_remote: bool = False) -> dict[str, object]:
    workflow = check_workflow(root)
    remotes = list_remotes(root)
    remote_ok = bool(remotes)
    ok = bool(workflow["ok"]) and (remote_ok or not require_remote)
    hints: list[str] = []
    if not workflow["ok"]:
        hint = str(workflow.get("hint") or "")
        if hint:
            hints.append(hint)
    if not remote_ok:
        hints.append(REMOTE_HINT)
    return {
        "ok": ok,
        "workflow": workflow,
        "remotes": remotes,
        "remote_configured": remote_ok,
        "require_remote": require_remote,
        "hints": hints,
        "blocked_reason": "" if ok else ("未配置 git remote" if require_remote and not remote_ok else "工作流检查未通过"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="远端 CI 就绪检查（工作流矩阵 + git remote）")
    parser.add_argument("--root", default=str(REPO_ROOT), help="仓库根目录")
    parser.add_argument("--require-remote", action="store_true", help="缺少 git remote 时视为未就绪（CI 使用）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)
    report = check(Path(args.root), require_remote=args.require_remote)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        workflow = report["workflow"]
        state = "就绪" if report["ok"] else "未就绪"
        print(f"远端 CI 检查：{state}")
        print(f"  工作流: {workflow['path']}" + ("（通过）" if workflow["ok"] else f"（缺失项：{', '.join(workflow['missing'])}）"))
        print(f"  git remote: {', '.join(report['remotes']) if report['remotes'] else '未配置'}")
        if report["hints"]:
            for hint in report["hints"]:
                print(f"  提示: {hint}")
        if report["blocked_reason"]:
            print(f"  阻塞: {report['blocked_reason']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
