"""
Persistent few-shot example store.

Examples are saved after each successful PR and retrieved (by keyword
similarity) at implementation time to give Claude concrete prior art
from this specific codebase.

Persistence strategy:
  - GitHub Actions context (GITHUB_REPOSITORY set): read/write
    examples/store.json in the agent repo via the GitHub Contents API
    so examples survive across workflow runs.
  - Local / CI without GITHUB_REPOSITORY: read/write a local
    examples/store.json file (persists for the lifetime of that process).
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

_STORE_PATH = "examples/store.json"
_MAX_STORED = 100  # rolling cap — oldest entries are dropped first

# Common English stop-words excluded from keyword matching
_STOP = frozenset(
    "a an the to in of for and or is it its be are was were will with "
    "that this on at by from as into".split()
)


# ── persistence helpers ────────────────────────────────────────────────────

def _is_actions() -> bool:
    return bool(os.getenv("GITHUB_REPOSITORY"))


def _load_local() -> list:
    try:
        return json.loads(Path(_STORE_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return []


def _save_local(examples: list) -> None:
    path = Path(_STORE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(examples, indent=2), encoding="utf-8")


def _load_remote() -> tuple:
    """Return (examples_list, file_sha_or_None). Never raises."""
    from github import Github, Auth, GithubException
    from agent.utils.retry import with_github_retry

    token = os.getenv("GITHUB_TOKEN")
    repo_name = os.getenv("GITHUB_REPOSITORY")
    if not token or not repo_name:
        return [], None
    try:
        repo = with_github_retry(Github(auth=Auth.Token(token)).get_repo, repo_name)
        f = with_github_retry(repo.get_contents, _STORE_PATH)
        data = json.loads(f.decoded_content.decode())
        return (data if isinstance(data, list) else []), f.sha
    except Exception:
        return [], None


def _save_remote(examples: list, sha) -> None:
    """Commit the examples file back to the agent repo. Never raises."""
    from github import Github, Auth
    from agent.utils.retry import with_github_retry

    token = os.getenv("GITHUB_TOKEN")
    repo_name = os.getenv("GITHUB_REPOSITORY")
    if not token or not repo_name:
        return
    try:
        repo = with_github_retry(Github(auth=Auth.Token(token)).get_repo, repo_name)
        body = json.dumps(examples, indent=2).encode()
        msg = "chore: update examples store [skip ci]"
        if sha:
            with_github_retry(repo.update_file, _STORE_PATH, msg, body, sha)
        else:
            with_github_retry(repo.create_file, _STORE_PATH, msg, body)
    except Exception:
        pass


# ── similarity ────────────────────────────────────────────────────────────

def _tokens(text: str) -> set:
    words = re.sub(r"[^a-z0-9]", " ", (text or "").lower()).split()
    return {w for w in words if w and w not in _STOP}


def _score(task: dict, example: dict) -> float:
    query = _tokens(task.get("title", "") + " " + (task.get("description") or "")[:300])
    target = _tokens(example.get("title", "") + " " + (example.get("description") or "")[:300])
    union = query | target
    if not union:
        return 0.0
    return len(query & target) / len(union)


# ── public API ────────────────────────────────────────────────────────────

def find_examples(task: dict, n: int = 2) -> list:
    """Return up to n most relevant past examples for the given task."""
    if _is_actions():
        examples, _ = _load_remote()
    else:
        examples = _load_local()

    if not examples:
        return []

    scored = sorted(
        ((ex, _score(task, ex)) for ex in examples),
        key=lambda x: x[1],
        reverse=True,
    )
    return [ex for ex, score in scored[:n] if score > 0]


def save_example(task: dict, changes: list, pr_url: str) -> None:
    """Persist a successful implementation for future few-shot retrieval."""
    entry = {
        "issue_number": task.get("number"),
        "title": task.get("title", ""),
        "description": (task.get("description") or "")[:500],
        "changes": [
            {
                "filepath": c.get("filepath", ""),
                "change_type": c.get("change_type", ""),
                "explanation": (c.get("explanation") or "")[:200],
            }
            for c in changes
        ],
        "pr_url": pr_url,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    if _is_actions():
        examples, sha = _load_remote()
        examples.append(entry)
        _save_remote(examples[-_MAX_STORED:], sha)
    else:
        examples = _load_local()
        examples.append(entry)
        _save_local(examples[-_MAX_STORED:])
