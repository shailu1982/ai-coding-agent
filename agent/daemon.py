import os
from github import Github, Auth, GithubException
from dotenv import load_dotenv
from rich import print
from rich.panel import Panel
from agent.utils.retry import with_github_retry
from agent.utils.config import load_repo_config
from agent.utils.summary import write_run_header, write_issue_success, write_issue_failure, write_no_work
from agent.utils.notifications import notify_success, notify_failure

load_dotenv("config/.env")

_LABEL_COLORS = {
    "ai-processing": "fbca04",
    "ai-done":       "0e8a16",
    "ai-failed":     "d73a4a",
}


def _ensure_label(repo, name: str):
    try:
        with_github_retry(repo.get_label, name)
    except GithubException:
        with_github_retry(repo.create_label, name, _LABEL_COLORS.get(name, "ededed"))


def _get_pending(repo, trigger_label: str, skip_labels: set):
    issues = with_github_retry(repo.get_issues, state="open", labels=[trigger_label])
    return [
        issue for issue in issues
        if not skip_labels.intersection({l.name for l in issue.labels})
    ]


def run():
    from agent.orchestrator import run_agent

    repo_path = os.getenv("REPO_LOCAL_PATH", ".")
    config = load_repo_config(repo_path)
    labels = config["labels"]

    trigger_label    = labels["trigger"]
    processing_label = labels["processing"]
    done_label       = labels["done"]
    failed_label     = labels["failed"]

    auth = Auth.Token(os.getenv("GITHUB_TOKEN"))
    g = Github(auth=auth)
    repo = with_github_retry(g.get_repo, os.getenv("GITHUB_REPO"))

    for label in (processing_label, done_label, failed_label):
        _ensure_label(repo, label)

    skip_labels = {processing_label, done_label, failed_label}
    pending = _get_pending(repo, trigger_label, skip_labels)

    if not pending:
        print("[dim]No pending issues — nothing to do.[/dim]")
        write_no_work()
        return

    write_run_header(os.getenv("GITHUB_REPO", ""), len(pending))

    print(Panel(
        f"[bold]Found {len(pending)} pending issue(s)[/bold]",
        expand=False
    ))

    for issue in pending:
        print(f"\n[bold cyan]━━ Issue #{issue.number}: {issue.title}[/bold cyan]")
        with_github_retry(issue.add_to_labels, processing_label)

        try:
            pr_url = run_agent(issue.number)

            with_github_retry(issue.remove_from_labels, trigger_label)
            with_github_retry(issue.remove_from_labels, processing_label)
            with_github_retry(issue.add_to_labels, done_label)
            with_github_retry(
                issue.create_comment,
                f"✅ **AI Agent completed this task automatically.**\n\n"
                f"Pull request: {pr_url}",
            )
            write_issue_success(issue.number, issue.title, pr_url)
            try:
                notify_success(issue.number, issue.title, pr_url, config)
            except Exception as notif_exc:
                print(f"  [yellow]⚠️  Slack notify failed: {notif_exc}[/yellow]")
            print(f"  [green]✅ Done — {pr_url}[/green]")

        except Exception as exc:
            with_github_retry(issue.remove_from_labels, processing_label)
            with_github_retry(issue.add_to_labels, failed_label)
            with_github_retry(
                issue.create_comment,
                f"❌ **AI Agent failed to complete this task.**\n\n"
                f"```\n{exc}\n```\n\n"
                f"Remove the `{failed_label}` label and re-add `{trigger_label}` to retry.",
            )
            write_issue_failure(issue.number, issue.title, exc)
            try:
                notify_failure(issue.number, issue.title, exc, config)
            except Exception as notif_exc:
                print(f"  [yellow]⚠️  Slack notify failed: {notif_exc}[/yellow]")
            print(f"  [red]❌ Failed: {exc}[/red]")


if __name__ == "__main__":
    run()
