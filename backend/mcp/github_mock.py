"""
Mock GitHub PR provider.

Interface is identical to what a real GitHub MCP integration would return.
To upgrade to real GitHub MCP:
  1. pip install mcp
  2. Set GITHUB_TOKEN in .env
  3. Replace get_pr_data() body with real MCP calls
  4. Everything else stays unchanged
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
    "mock://pr/style-only": PRData(
        url="mock://pr/style-only",
        title="Fix variable naming",
        author="dev_carol",
        base_branch="main",
        head_branch="fix/naming",
        files_changed=["utils/helpers.py"],
        language="Python",
        diff="""diff --git a/utils/helpers.py b/utils/helpers.py
--- a/utils/helpers.py
+++ b/utils/helpers.py
@@ -3,6 +3,6 @@
-def calc(x,y,z):
-    r = x+y
-    return r*z
+def calculate_weighted_sum(base: float, offset: float, weight: float) -> float:
+    total = base + offset
+    return total * weight
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
    Fetch PR by URL. Returns mock data or falls back to treating
    the URL string as a raw diff for manual testing.
    """
    if pr_url in MOCK_PRS:
        return MOCK_PRS[pr_url]
    # Unknown URL → treat as raw diff input (useful for ad-hoc testing)
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