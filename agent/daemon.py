import os
from dotenv import load_dotenv
from rich import print
from rich.panel import Panel
from agent.utils.github import get_repo, ensure_label, process_issue_success, process_issue_failure
from agent.utils.retry import with_github_retry
from agent.utils.config import load_repo_config
from agent.utils.summary import write_run_header, write_issue_success, write_issue_failure, write_no_work
from agent.utils.notifications import notify_success, notify_failure

load_dotenv("config/.env")


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

    auth_token = os.getenv("GITHUB_TOKEN")
    if not auth_token:
        raise RuntimeError("GITHUB_TOKEN is not set")

    repo = get_repo()

    for label in (processing_label, done_label, failed_label):
        ensure_label(repo, label)

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

            process_issue_success(issue, labels, pr_url)
            write_issue_success(issue.number, issue.title, pr_url)
            try:
                notify_success(issue.number, issue.title, pr_url, config)
            except Exception as notif_exc:
                print(f"  [yellow]⚠️  Slack notify failed: {notif_exc}[/yellow]")
            print(f"  [green]✅ Done — {pr_url}[/green]")

        except Exception as exc:
            process_issue_failure(issue, labels, exc)
            write_issue_failure(issue.number, issue.title, exc)
            try:
                notify_failure(issue.number, issue.title, exc, config)
            except Exception as notif_exc:
                print(f"  [yellow]⚠️  Slack notify failed: {notif_exc}[/yellow]")
            print(f"  [red]❌ Failed: {exc}[/red]")


if __name__ == "__main__":
    run()
