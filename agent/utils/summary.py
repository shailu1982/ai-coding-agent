import os
from datetime import datetime, timezone


def _summary_file() -> str | None:
    return os.getenv("GITHUB_STEP_SUMMARY")


def _append(text: str) -> None:
    path = _summary_file()
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        f.write(text + "\n")


def write_run_header(repo: str, issue_count: int) -> None:
    """Write the top-level header once per daemon run."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    _append(f"# 🤖 AI Coding Agent — {now}\n")
    _append(f"**Repo:** `{repo}` &nbsp;|&nbsp; **Issues processed:** {issue_count}\n")
    _append("---\n")


def write_issue_success(issue_number: int, title: str, pr_url: str) -> None:
    _append(
        f"### ✅ Issue #{issue_number} — {title}\n"
        f"| | |\n"
        f"|---|---|\n"
        f"| **Status** | Success |\n"
        f"| **Pull Request** | [{pr_url}]({pr_url}) |\n"
    )


def write_issue_failure(issue_number: int, title: str, error: str) -> None:
    short = str(error)[:400].replace("`", "'")
    _append(
        f"### ❌ Issue #{issue_number} — {title}\n"
        f"| | |\n"
        f"|---|---|\n"
        f"| **Status** | Failed |\n"
        f"| **Error** | `{short}` |\n"
    )


def write_no_work() -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    _append(f"# 🤖 AI Coding Agent — {now}\n")
    _append("No pending issues found — nothing to do.\n")
