"""PR data provider and smart router for mock, evaluation, and GitHub inputs."""
from __future__ import annotations

import re
from dataclasses import dataclass

from backend.observability.logger import log_structured


@dataclass
class PRData:
    url: str
    title: str
    author: str
    base_branch: str
    head_branch: str
    files_changed: list[str]
    language: str
    diff: str


MOCK_PRS: dict[str, PRData] = {
    "mock://pr/security-issue": PRData(
        url="mock://pr/security-issue",
        title="Add user authentication endpoint",
        author="dev_alice",
        base_branch="main",
        head_branch="feat/auth",
        files_changed=["auth/views.py", "auth/models.py"],
        language="Python",
        diff="""diff --git a/auth/views.py b/auth/views.py
--- a/auth/views.py
+++ b/auth/views.py
@@ -1,5 +1,28 @@
+import hashlib
+from flask import request, jsonify
+from auth.models import User
+
+def login():
+    username = request.args.get('username')
+    password = request.args.get('password')
+    user = User.query.filter_by(username=username).first()
+    if user and user.password == hashlib.md5(password.encode()).hexdigest():
+        return jsonify({"token": "hardcoded_secret_token_12345"})
+    return jsonify({"error": "invalid credentials"}), 401
+
+def get_user_data(user_id):
+    query = f"SELECT * FROM users WHERE id = {user_id}"
+    result = db.execute(query)
+    return result
""",
    ),
    "mock://pr/clean-refactor": PRData(
        url="mock://pr/clean-refactor",
        title="Refactor data processing pipeline",
        author="dev_bob",
        base_branch="main",
        head_branch="refactor/pipeline",
        files_changed=["pipeline/processor.py"],
        language="Python",
        diff="""diff --git a/pipeline/processor.py b/pipeline/processor.py
--- a/pipeline/processor.py
+++ b/pipeline/processor.py
@@ -10,15 +10,22 @@
-def process(data):
-    result = []
-    for i in range(len(data)):
-        if data[i] != None:
-            result.append(data[i] * 2)
-    return result
+from typing import Optional
+
+def process_items(data: list[Optional[int]]) -> list[int]:
+    \"\"\"Double all non-null integers in the input list.\"\"\"
+    return [item * 2 for item in data if item is not None]
""",
    ),
    "mock://pr/typescript-react": PRData(
        url="mock://pr/typescript-react",
        title="Add user profile component with hooks",
        author="dev_carol",
        base_branch="main",
        head_branch="feat/user-profile",
        files_changed=["src/components/UserProfile.tsx", "src/hooks/useUser.ts"],
        language="TypeScript",
        diff="""diff --git a/src/components/UserProfile.tsx b/src/components/UserProfile.tsx
--- a/src/components/UserProfile.tsx
+++ b/src/components/UserProfile.tsx
@@ -0,0 +1,34 @@
+import React, { useEffect, useState } from 'react'
+
+export function UserProfile({ userId }: { userId: any }) {
+  const [user, setUser] = useState(null)
+
+  useEffect(() => {
+    fetch('/api/users/' + userId)
+      .then(r => r.json())
+      .then(data => setUser(data))
+  }, [])
+
+  if (!user) return <div>Loading...</div>
+
+  return (
+    <div dangerouslySetInnerHTML={{ __html: user.bio }} />
+  )
+}
""",
    ),
    "mock://pr/empty": PRData(
        url="mock://pr/empty",
        title="Empty PR",
        author="dev_dave",
        base_branch="main",
        head_branch="feat/empty",
        files_changed=[],
        language="Unknown",
        diff="",
    ),
}

_DIFF_FILE_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$", re.MULTILINE)


def _extract_files_from_diff(diff: str) -> list[str]:
    files: list[str] = []
    for _, new_path in _DIFF_FILE_RE.findall(diff):
        normalized = new_path.strip()
        if normalized not in files:
            files.append(normalized)
    return files


def _detect_language(files_changed: list[str]) -> str:
    if not files_changed:
        return "Unknown"
    try:
        from backend.mcp.github_client import detect_language

        return detect_language(files_changed)
    except Exception:
        return "Unknown"


def _evaluation_pr(pr_url: str) -> PRData | None:
    if not pr_url.startswith("eval://"):
        return None

    try:
        from evaluation.scenarios import SCENARIOS
    except Exception:
        return None

    scenario = next((item for item in SCENARIOS if item["id"] == pr_url), None)
    if scenario is None:
        return None

    files_changed = _extract_files_from_diff(scenario["diff"])
    language = _detect_language(files_changed)
    return PRData(
        url=pr_url,
        title=scenario["name"],
        author="eval_bot",
        base_branch="main",
        head_branch="evaluation",
        files_changed=files_changed,
        language=language,
        diff=scenario["diff"],
    )


def _raw_diff_pr(pr_url: str) -> PRData:
    files_changed = _extract_files_from_diff(pr_url)
    language = _detect_language(files_changed)
    return PRData(
        url=pr_url,
        title="Custom PR",
        author="unknown",
        base_branch="main",
        head_branch="feature",
        files_changed=files_changed,
        language=language if language != "Unknown" else "Unknown",
        diff=pr_url,
    )


def get_pr_data(pr_url: str) -> PRData:
    """
    Router:
      1. mock:// -> built-in mock data
      2. eval:// -> evaluation scenario diffs
      3. github.com PR URL -> live GitHub API
      4. anything else -> treat input as raw diff text
    """
    if pr_url in MOCK_PRS:
        return MOCK_PRS[pr_url]

    evaluation_pr = _evaluation_pr(pr_url)
    if evaluation_pr is not None:
        return evaluation_pr

    if pr_url.startswith("https://github.com/") and "/pull/" in pr_url:
        try:
            from backend.config import settings
            from backend.mcp.github_client import get_real_pr_data

            token = getattr(settings, "github_token", None) or None
            return get_real_pr_data(pr_url, token=token)
        except ValueError as exc:
            error_msg = str(exc)
            log_structured(
                "ERROR",
                "github_fetch_error",
                pr_url=pr_url,
                error_type=type(exc).__name__,
                error=error_msg,
                is_rate_limit="rate limit exceeded" in error_msg.lower(),
            )
            return PRData(
                url=pr_url,
                title="GitHub fetch error",
                author="system",
                base_branch="main",
                head_branch="feature",
                files_changed=[],
                language="Unknown",
                diff=(
                    "# ERROR: GitHub fetch failed\n"
                    f"# Reason: {error_msg}\n"
                    "# Check GITHUB_TOKEN and repository access."
                ),
            )
        except Exception as exc:
            log_structured(
                "ERROR",
                "github_fetch_fallback",
                pr_url=pr_url,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return PRData(
                url=pr_url,
                title="GitHub fetch failed",
                author="unknown",
                base_branch="main",
                head_branch="feature",
                files_changed=[],
                language="Unknown",
                diff=(
                    "# ERROR: Could not fetch PR from GitHub\n"
                    f"# Reason: {exc}\n"
                    "# Check GITHUB_TOKEN in .env and ensure the PR is accessible."
                ),
            )

    return _raw_diff_pr(pr_url)
