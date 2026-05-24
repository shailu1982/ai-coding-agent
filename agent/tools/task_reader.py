import os
from github import Github, Auth
from dotenv import load_dotenv

load_dotenv("config/.env")

def get_task(issue_number: int) -> dict:
    auth = Auth.Token(os.getenv("GITHUB_TOKEN"))
    g = Github(auth=auth)
    repo = g.get_repo(os.getenv("GITHUB_REPO"))
    issue = repo.get_issue(number=issue_number)

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


# Quick test
if __name__ == "__main__":
    from rich import print

    print("\n[bold]Fetching issue #18...[/bold]")
    raw = get_task(18)
    print("\n[bold]Raw task:[/bold]")
    print(raw)

    parsed = parse_task(raw)
    print("\n[bold]Parsed task:[/bold]")
    print(parsed)

    criteria = get_criteria(parsed)
    print("\n[bold]Acceptance criteria:[/bold]")
    for i, c in enumerate(criteria, 1):
        print(f"  {i}. {c}")