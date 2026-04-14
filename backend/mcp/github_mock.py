"""PR data provider and smart router for mock and GitHub-backed inputs."""
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


def get_pr_data(pr_url: str) -> PRData:
    """
    Smart router:
      1. mock:// -> built-in mock data
      2. github.com PR URL -> real GitHub API
      3. anything else -> raw diff fallback
    """
    if pr_url in MOCK_PRS:
        return MOCK_PRS[pr_url]

    if pr_url.startswith("https://github.com/") and "/pull/" in pr_url:
        try:
            from backend.config import settings
            from backend.mcp.github_client import get_real_pr_data

            token = getattr(settings, "github_token", None) or None
            return get_real_pr_data(pr_url, token=token)
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

    return PRData(
        url=pr_url,
        title="Custom PR",
        author="unknown",
        base_branch="main",
        head_branch="feature",
        files_changed=["unknown.py"],
        language="Python",
        diff=pr_url,
    )
