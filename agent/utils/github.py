"""
Shared GitHub helpers.

Centralises `get_repo()`, label utilities, and the `process_issue()` wrapper
so that daemon.py, discover.py, and worker.py don't duplicate them.
"""

import os

from github import Github, Auth, GithubException

from agent.utils.retry import with_github_retry

LABEL_COLORS = {
    "ai-processing": "fbca04",
    "ai-done":       "0e8a16",
    "ai-failed":     "d73a4a",
}


def get_repo():
    """Return a PyGithub Repository object for GITHUB_REPO, with retry."""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN is not set. "
            "Add it to config/.env or export it as an environment variable."
        )
    auth = Auth.Token(token)
    g = Github(auth=auth)
    return with_github_retry(g.get_repo, os.getenv("GITHUB_REPO"))


def ensure_label(repo, name: str) -> None:
    """Create the label if it doesn't already exist on the repo."""
    try:
        with_github_retry(repo.get_label, name)
    except GithubException:
        with_github_retry(repo.create_label, name, LABEL_COLORS.get(name, "ededed"))


def process_issue_success(issue, labels: dict, pr_url: str) -> None:
    """Update labels and comment on a successfully processed issue."""
    for label_name in (labels["trigger"], labels["processing"]):
        try:
            with_github_retry(issue.remove_from_labels, label_name)
        except GithubException:
            pass  # label was already removed (e.g., by a human)
    with_github_retry(issue.add_to_labels, labels["done"])
    with_github_retry(
        issue.create_comment,
        f"✅ **AI Agent completed this task automatically.**\n\n"
        f"Pull request: {pr_url}",
    )


def process_issue_failure(issue, labels: dict, exc: Exception) -> None:
    """Update labels and comment on a failed issue."""
    try:
        with_github_retry(issue.remove_from_labels, labels["processing"])
    except GithubException:
        pass  # label was already removed
    with_github_retry(issue.add_to_labels, labels["failed"])
    with_github_retry(
        issue.create_comment,
        f"❌ **AI Agent failed to complete this task.**\n\n"
        f"```\n{exc}\n```\n\n"
        f"Remove the `{labels['failed']}` label and re-add `{labels['trigger']}` to retry.",
    )
