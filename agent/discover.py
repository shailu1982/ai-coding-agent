import json
import os
from dotenv import load_dotenv
from agent.utils.github import get_repo, ensure_label
from agent.utils.retry import with_github_retry
from agent.utils.config import load_repo_config

load_dotenv("config/.env")


def main() -> None:
    """Discover pending issues, claim them, and output a JSON matrix.

    Finds all pending issues, claims them with the 'processing' label
    (to prevent double-pickup on the next cron tick), then prints a
    JSON array of issue numbers to stdout for the Actions matrix.
    """
    repo_path = os.getenv("REPO_LOCAL_PATH", ".")
    config = load_repo_config(repo_path)
    labels = config["labels"]

    repo = get_repo()

    for label_name in (labels["processing"], labels["done"], labels["failed"]):
        ensure_label(repo, label_name)

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
