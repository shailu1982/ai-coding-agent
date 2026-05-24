import json
import os
import urllib.error
import urllib.request


def _actions_run_url() -> str:
    """Build the GitHub Actions run URL from standard env vars (set automatically in Actions)."""
    server = os.getenv("GITHUB_SERVER_URL", "https://github.com")
    repo = os.getenv("GITHUB_REPOSITORY", "")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    if repo and run_id:
        return f"{server}/{repo}/actions/runs/{run_id}"
    return ""


def _post_slack(webhook_url: str, payload: dict) -> None:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status not in (200, 204):
                raise RuntimeError(f"Slack responded {resp.status}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Slack webhook request failed: {exc}") from exc


def notify_success(issue_number: int, title: str, pr_url: str, config: dict) -> None:
    notif = config.get("notifications", {})
    webhook = notif.get("slack_webhook")
    if not webhook or not notif.get("on_success", False):
        return

    run_url = _actions_run_url()
    run_link = f" | <{run_url}|Actions run>" if run_url else ""

    _post_slack(webhook, {
        "text": f"✅ *AI Agent — Issue #{issue_number} complete*",
        "attachments": [{
            "color": "good",
            "fields": [
                {"title": "Issue", "value": f"#{issue_number} {title}", "short": False},
                {"title": "Pull Request", "value": pr_url, "short": False},
            ],
            "footer": f"AI Coding Agent{run_link}",
        }],
    })


def notify_failure(issue_number: int, title: str, error: str, config: dict) -> None:
    notif = config.get("notifications", {})
    webhook = notif.get("slack_webhook")
    if not webhook or not notif.get("on_failure", True):
        return

    run_url = _actions_run_url()
    run_link = f" | <{run_url}|Actions run>" if run_url else ""
    short_error = str(error)[:300].replace("`", "'")

    _post_slack(webhook, {
        "text": f"❌ *AI Agent — Issue #{issue_number} failed*",
        "attachments": [{
            "color": "danger",
            "fields": [
                {"title": "Issue", "value": f"#{issue_number} {title}", "short": False},
                {"title": "Error", "value": f"```{short_error}```", "short": False},
            ],
            "footer": f"AI Coding Agent{run_link}",
        }],
    })
