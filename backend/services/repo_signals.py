from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

from backend.config import settings
from backend.graph.state import RepoLintIssue, RepoSignals
from backend.mcp.github_client import GHPRRef, parse_github_url
from backend.observability.logger import log_structured
from backend.utils.cache import TTLCache, build_cache_backend, build_cache_key

_MAX_LINT_ISSUES = 8
_REPO_SIGNAL_CACHE_KEY = "repo_signals_v1"
_CHECKOUT_ROOT = Path(tempfile.gettempdir()) / "pr_critic_repo_checkouts"


def _default_repo_signals(
    *,
    checkout_status: str,
    lint_status: str,
    file_types: list[str] | None = None,
    lint_issues: list[RepoLintIssue] | None = None,
    summary: str = "",
) -> RepoSignals:
    issues = list(lint_issues or [])
    return {
        "checkout_status": checkout_status,
        "lint_status": lint_status,
        "file_types": list(file_types or []),
        "lint_issue_count": len(issues),
        "lint_issues": issues,
        "summary": summary,
    }


try:
    _REPO_SIGNAL_CACHE = build_cache_backend(
        settings.cache_backend,
        name="repo_signals",
        ttl_seconds=settings.caches.pr_ttl_seconds,
        max_size=32,
    )
except NotImplementedError:
    log_structured(
        "WARNING",
        "cache_backend_fallback",
        requested_backend=settings.cache_backend,
        cache="repo_signals",
    )
    _REPO_SIGNAL_CACHE = TTLCache(
        "repo_signals",
        settings.caches.pr_ttl_seconds,
        max_size=32,
    )


def _normalize_rel_path(path: str, *, root: Path) -> str:
    normalized = str(path).replace("\\", "/").strip()
    try:
        relative = Path(normalized)
        if relative.is_absolute():
            return str(relative.relative_to(root)).replace("\\", "/")
    except Exception:
        pass
    return normalized or "unknown"


def _collect_file_types(files_changed: Iterable[str]) -> list[str]:
    extensions: list[str] = []
    for file_path in files_changed:
        suffix = Path(file_path).suffix.lower().lstrip(".")
        if not suffix:
            continue
        if suffix not in extensions:
            extensions.append(suffix)
    return extensions


def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout_seconds: float | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        check=check,
        timeout=timeout_seconds or settings.repo_signal_timeout_seconds,
    )


def _git_executable() -> str | None:
    return shutil.which("git")


def _npx_executable() -> str | None:
    return shutil.which("npx.cmd") or shutil.which("npx")


def _repo_dir(ref: GHPRRef) -> Path:
    return _CHECKOUT_ROOT / f"{ref.owner}_{ref.repo}_{ref.number}"


def _is_valid_git_checkout(repo_dir: Path) -> bool:
    git_dir = repo_dir / ".git"
    return git_dir.is_dir() and (git_dir / "HEAD").exists() and (git_dir / "config").exists()


def _remove_checkout_dir(repo_dir: Path) -> None:
    resolved_root = _CHECKOUT_ROOT.resolve()
    resolved_repo = repo_dir.resolve()
    if resolved_repo == resolved_root or resolved_root not in resolved_repo.parents:
        raise RuntimeError(f"Refusing to remove checkout outside {_CHECKOUT_ROOT}: {repo_dir}")
    shutil.rmtree(resolved_repo, ignore_errors=True)


def _checkout_pr(ref: GHPRRef) -> Path:
    git = _git_executable()
    if git is None:
        raise RuntimeError("git is not available")

    repo_dir = _repo_dir(ref)
    repo_url = f"https://github.com/{ref.owner}/{ref.repo}.git"
    _CHECKOUT_ROOT.mkdir(parents=True, exist_ok=True)

    if repo_dir.exists() and not _is_valid_git_checkout(repo_dir):
        _remove_checkout_dir(repo_dir)

    if not _is_valid_git_checkout(repo_dir):
        _run(
            [
                git,
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                "--depth",
                "1",
                repo_url,
                str(repo_dir),
            ]
        )

    _run(
        [
            git,
            "fetch",
            "--depth",
            "1",
            "origin",
            f"refs/pull/{ref.number}/head",
        ],
        cwd=repo_dir,
    )
    _run([git, "checkout", "--force", "FETCH_HEAD"], cwd=repo_dir)
    return repo_dir


def _python_files(files_changed: Iterable[str]) -> list[str]:
    return [file_path for file_path in files_changed if file_path.lower().endswith((".py", ".pyi"))]


def _node_files(files_changed: Iterable[str]) -> list[str]:
    return [
        file_path
        for file_path in files_changed
        if file_path.lower().endswith((".js", ".jsx", ".ts", ".tsx"))
    ]


def _parse_flake8_output(output: str, *, repo_root: Path) -> list[RepoLintIssue]:
    issues: list[RepoLintIssue] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(":", 3)
        if len(parts) < 4:
            continue
        file_path, line_no, _column, remainder = parts
        detail = remainder.strip().split(" ", 1)
        code = detail[0] if detail else "FLAKE8"
        message = detail[1] if len(detail) > 1 else remainder.strip()
        try:
            parsed_line = int(line_no)
        except ValueError:
            parsed_line = 0
        issues.append(
            {
                "tool": "flake8",
                "file": _normalize_rel_path(file_path, root=repo_root),
                "line": parsed_line,
                "code": code,
                "message": message,
            }
        )
    return issues


def _has_eslint_config(repo_root: Path) -> bool:
    config_names = (
        "eslint.config.js",
        "eslint.config.mjs",
        ".eslintrc",
        ".eslintrc.js",
        ".eslintrc.cjs",
        ".eslintrc.json",
        ".eslintrc.yml",
        ".eslintrc.yaml",
    )
    if any((repo_root / name).exists() for name in config_names):
        return True

    package_json = repo_root / "package.json"
    if not package_json.exists():
        return False

    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False

    return "eslintConfig" in data


def _parse_eslint_output(output: str, *, repo_root: Path) -> list[RepoLintIssue]:
    issues: list[RepoLintIssue] = []
    if not output.strip():
        return issues
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return issues

    for file_result in payload:
        file_path = _normalize_rel_path(file_result.get("filePath", ""), root=repo_root)
        for message in file_result.get("messages", []):
            issues.append(
                {
                    "tool": "eslint",
                    "file": file_path,
                    "line": int(message.get("line") or 0),
                    "code": str(message.get("ruleId") or "eslint"),
                    "message": str(message.get("message") or ""),
                }
            )
    return issues


def _run_python_lint(repo_root: Path, files_changed: Iterable[str]) -> tuple[str, list[RepoLintIssue]]:
    python_files = [file_path for file_path in _python_files(files_changed) if (repo_root / file_path).exists()]
    if not python_files:
        return "not_applicable", []
    if importlib.util.find_spec("flake8") is None:
        return "unavailable", []

    result = _run(
        [sys.executable, "-m", "flake8", *python_files],
        cwd=repo_root,
        check=False,
    )
    if result.returncode not in {0, 1}:
        return "failed", []
    issues = _parse_flake8_output(result.stdout, repo_root=repo_root)
    return ("issues" if issues else "clean"), issues


def _run_node_lint(repo_root: Path, files_changed: Iterable[str]) -> tuple[str, list[RepoLintIssue]]:
    node_files = [file_path for file_path in _node_files(files_changed) if (repo_root / file_path).exists()]
    if not node_files:
        return "not_applicable", []
    npx = _npx_executable()
    if npx is None or not _has_eslint_config(repo_root):
        return "unavailable", []

    result = _run(
        [npx, "--no-install", "eslint", "--format", "json", *node_files],
        cwd=repo_root,
        check=False,
    )
    if result.returncode not in {0, 1}:
        return "failed", []
    issues = _parse_eslint_output(result.stdout, repo_root=repo_root)
    return ("issues" if issues else "clean"), issues


def _build_summary(
    *,
    checkout_status: str,
    file_types: list[str],
    python_status: str,
    python_issues: list[RepoLintIssue],
    node_status: str,
    node_issues: list[RepoLintIssue],
) -> str:
    parts: list[str] = []
    if file_types:
        parts.append(f"Changed file types: {', '.join(file_types)}.")
    if checkout_status != "ready":
        parts.append(f"Repository checkout status: {checkout_status}.")
        return " ".join(parts).strip()

    if python_status not in {"not_applicable", "unavailable"}:
        parts.append(f"flake8 status: {python_status} ({len(python_issues)} issue(s)).")
    elif python_status == "unavailable":
        parts.append("flake8 unavailable for Python signals.")

    if node_status not in {"not_applicable", "unavailable"}:
        parts.append(f"eslint status: {node_status} ({len(node_issues)} issue(s)).")
    elif node_status == "unavailable":
        parts.append("eslint unavailable for Node/TS signals.")

    if python_issues or node_issues:
        preview = python_issues + node_issues
        formatted = "; ".join(
            f"{issue['tool']} {issue['file']}:{issue['line']} {issue['code']} {issue['message']}"
            for issue in preview[:3]
        )
        parts.append(f"Top lint findings: {formatted}.")

    return " ".join(part for part in parts if part).strip()


def _collect_repo_signals(pr_url: str, files_changed: list[str]) -> RepoSignals:
    ref = parse_github_url(pr_url)
    file_types = _collect_file_types(files_changed)
    if ref is None:
        return _default_repo_signals(
            checkout_status="not_applicable",
            lint_status="not_applicable",
            file_types=file_types,
            summary=(
                f"Changed file types: {', '.join(file_types)}."
                if file_types
                else "Repository checkout not requested for this source."
            ),
        )

    try:
        repo_root = _checkout_pr(ref)
    except Exception as exc:
        log_structured(
            "WARNING",
            "repo_signals_checkout_failed",
            pr_url=pr_url,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return _default_repo_signals(
            checkout_status="failed",
            lint_status="unavailable",
            file_types=file_types,
            summary=(
                f"Changed file types: {', '.join(file_types)}. "
                f"Repository checkout failed: {exc}"
            ).strip(),
        )

    python_status, python_issues = _run_python_lint(repo_root, files_changed)
    node_status, node_issues = _run_node_lint(repo_root, files_changed)
    lint_issues = (python_issues + node_issues)[:_MAX_LINT_ISSUES]
    lint_status = "issues" if lint_issues else "clean"
    if python_status == "failed" and node_status == "failed":
        lint_status = "failed"
    elif lint_status == "clean" and python_status == "unavailable" and node_status == "unavailable":
        lint_status = "unavailable"
    elif lint_status == "clean" and python_status == "not_applicable" and node_status == "not_applicable":
        lint_status = "not_applicable"

    return _default_repo_signals(
        checkout_status="ready",
        lint_status=lint_status,
        file_types=file_types,
        lint_issues=lint_issues,
        summary=_build_summary(
            checkout_status="ready",
            file_types=file_types,
            python_status=python_status,
            python_issues=python_issues,
            node_status=node_status,
            node_issues=node_issues,
        ),
    )


def collect_repo_signals(
    pr_url: str,
    files_changed: list[str],
    *,
    request_cache_key: str = "",
) -> RepoSignals:
    cache_key = build_cache_key(
        request_cache_key or pr_url,
        ",".join(files_changed),
        _REPO_SIGNAL_CACHE_KEY,
    )
    signals, cache_hit = _REPO_SIGNAL_CACHE.get_or_compute(
        cache_key,
        lambda: _collect_repo_signals(pr_url, files_changed),
    )
    log_structured(
        "INFO",
        "repo_signals_collected",
        pr_url=pr_url,
        checkout_status=signals["checkout_status"],
        lint_status=signals["lint_status"],
        lint_issue_count=signals["lint_issue_count"],
        file_types=signals["file_types"],
        cache_hit=cache_hit,
    )
    return signals
