"""
Single-issue worker — called by each matrix job in the Actions workflow.

The discover step has already added the 'processing' label, so this
script just runs the pipeline and updates labels on completion.
"""
import argparse
import os
import sys
from dotenv import load_dotenv
from github import Github, Auth
from agent.utils.retry import with_github_retry
from agent.utils.config import load_repo_config
from agent.utils.summary import write_run_header, write_issue_success, write_issue_failure
from agent.utils.notifications import notify_success, notify_failure

load_dotenv("config/.env")


def main() -> None:
    parser = argparse.ArgumentParser(description="Process a single GitHub issue")
    parser.add_argument("--issue", type=int, required=True, help="Issue number to process")
    args = parser.parse_args()

    from agent.orchestrator import run_agent

    repo_path = os.getenv("REPO_LOCAL_PATH", ".")
    config = load_repo_config(repo_path)
    labels = config["labels"]

    auth = Auth.Token(os.getenv("GITHUB_TOKEN"))
    g = Github(auth=auth)
    repo = with_github_retry(g.get_repo, os.getenv("GITHUB_REPO"))
    issue = with_github_retry(repo.get_issue, number=args.issue)

    write_run_header(os.getenv("GITHUB_REPO", ""), 1)

    try:
        pr_url = run_agent(args.issue)

        with_github_retry(issue.remove_from_labels, labels["trigger"])
        with_github_retry(issue.remove_from_labels, labels["processing"])
        with_github_retry(issue.add_to_labels, labels["done"])
        with_github_retry(
            issue.create_comment,
            f"✅ **AI Agent completed this task automatically.**\n\n"
            f"Pull request: {pr_url}",
        )

        write_issue_success(args.issue, issue.title, pr_url)
        try:
            notify_success(args.issue, issue.title, pr_url, config)
        except Exception as notif_exc:
            print(f"⚠️  Slack notify failed: {notif_exc}", file=sys.stderr)

        print(f"✅ Done — {pr_url}")

    except Exception as exc:
        with_github_retry(issue.remove_from_labels, labels["processing"])
        with_github_retry(issue.add_to_labels, labels["failed"])
        with_github_retry(
            issue.create_comment,
            f"❌ **AI Agent failed to complete this task.**\n\n"
            f"```\n{exc}\n```\n\n"
            f"Remove the `{labels['failed']}` label and re-add `{labels['trigger']}` to retry.",
        )

        write_issue_failure(args.issue, issue.title, exc)
        try:
            notify_failure(args.issue, issue.title, exc, config)
        except Exception as notif_exc:
            print(f"⚠️  Slack notify failed: {notif_exc}", file=sys.stderr)

        print(f"❌ Failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
