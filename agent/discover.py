"""
Discovery step for parallel processing.

Finds all pending issues, claims them with the 'processing' label
(to prevent double-pickup on the next cron tick), then prints a
JSON array of issue numbers to stdout for the Actions matrix.
"""
import json
import os
import sys
from dotenv import load_dotenv
from github import Github, Auth, GithubException
from agent.utils.retry import with_github_retry
from agent.utils.config import load_repo_config

load_dotenv("config/.env")

_LABEL_COLORS = {
    "ai-processing": "fbca04",
    "ai-done":       "0e8a16",
    "ai-failed":     "d73a4a",
}


def _ensure_label(repo, name: str) -> None:
    try:
        with_github_retry(repo.get_label, name)
    except GithubException:
        with_github_retry(repo.create_label, name, _LABEL_COLORS.get(name, "ededed"))


def main() -> None:
    repo_path = os.getenv("REPO_LOCAL_PATH", ".")
    config = load_repo_config(repo_path)
    labels = config["labels"]

    auth = Auth.Token(os.getenv("GITHUB_TOKEN"))
    g = Github(auth=auth)
    repo = with_github_retry(g.get_repo, os.getenv("GITHUB_REPO"))

    for label_name in (labels["processing"], labels["done"], labels["failed"]):
        _ensure_label(repo, label_name)

    skip = {labels["processing"], labels["done"], labels["failed"]}
    issues = with_github_retry(repo.get_issues, state="open", labels=[labels["trigger"]])
    pending = [i for i in issues if not skip.intersection({l.name for l in i.labels})]

    if not pending:
        print("[]", flush=True)
        return

    # Claim each issue immediately so the next cron tick won't double-pick them
    for issue in pending:
        with_github_retry(issue.add_to_labels, labels["processing"])

    print(json.dumps([i.number for i in pending]), flush=True)


if __name__ == "__main__":
    main()
