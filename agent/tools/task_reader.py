from agent.utils.github import get_repo
from agent.utils.retry import with_github_retry


def get_task(issue_number: int) -> dict:
    repo = get_repo()
    issue = with_github_retry(repo.get_issue, number=issue_number)

    return {
        "number": issue.number,
        "title": issue.title,
        "body": issue.body,
        "labels": [label.name for label in issue.labels],
        "state": issue.state,
        "url": issue.html_url
    }

def parse_task(task: dict) -> dict:
    body = task.get("body") or ""
    lines = body.split("\n")

    description = []
    criteria = []
    in_criteria = False

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if "acceptance criteria" in line.lower():
            in_criteria = True
            continue
        if in_criteria and (
            line.startswith("- [ ]") or
            line.startswith("- [x]") or
            line.startswith("- ") or
            line.startswith("* ")
        ):
            cleaned = line.lstrip("-").lstrip("*").strip()
            cleaned = cleaned.replace("[ ]", "").replace("[x]", "").strip()
            criteria.append(cleaned)
        elif not in_criteria:
            description.append(line)

    return {
        "number": task["number"],
        "title": task["title"],
        "url": task["url"],
        "labels": task["labels"],
        "description": "\n".join(description),
        "acceptance_criteria": criteria
    }


def get_criteria(task: dict) -> list:
    return task.get("acceptance_criteria") or []


if __name__ == "__main__":
    import argparse
    from rich import print

    parser = argparse.ArgumentParser(description="Fetch and parse a GitHub issue")
    parser.add_argument("--issue", type=int, required=True, help="GitHub issue number")
    args = parser.parse_args()

    raw = get_task(args.issue)
    parsed = parse_task(raw)
    print(parsed)

    criteria = get_criteria(parsed)
    for i, c in enumerate(criteria, 1):
        print(f"  {i}. {c}")