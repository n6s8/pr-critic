"""
mcp/github_mock.py — PR data provider.

Routes:
  - mock://...   → built-in mock data (always works, no token needed)
  - https://github.com/...  → real GitHub API (requires httpx; token optional)
  - anything else           → treat the string as a raw diff for ad-hoc testing
"""
from dataclasses import dataclass, field


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
      1. mock:// → built-in mock data
      2. github.com PR URL → real GitHub API
      3. anything else → raw diff fallback
    """
    # 1. Mock URLs
    if pr_url in MOCK_PRS:
        return MOCK_PRS[pr_url]

    # 2. Real GitHub URLs
    if pr_url.startswith("https://github.com/") and "/pull/" in pr_url:
        try:
            from backend.mcp.github_client import get_real_pr_data
            from backend.config import settings
            token = getattr(settings, "github_token", None) or None
            return get_real_pr_data(pr_url, token=token)
        except Exception as exc:
            # If GitHub fetch fails (bad token, network error, private repo),
            # return an error-state PRData rather than crashing the whole pipeline
            return PRData(
                url=pr_url,
                title="GitHub fetch failed",
                author="unknown",
                base_branch="main",
                head_branch="feature",
                files_changed=[],
                language="Unknown",
                diff=f"# ERROR: Could not fetch PR from GitHub\n# Reason: {exc}\n"
                     f"# Check GITHUB_TOKEN in .env and ensure the PR is accessible.",
            )

    # 3. Raw diff fallback (useful for testing)
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