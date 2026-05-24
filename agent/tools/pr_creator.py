import os
import subprocess
from github import Github, Auth
from dotenv import load_dotenv
from agent.utils.retry import RetryingClient, with_github_retry

load_dotenv("config/.env")

client = RetryingClient(api_key=os.getenv("ANTHROPIC_API_KEY"))


def get_repo():
    auth = Auth.Token(os.getenv("GITHUB_TOKEN"))
    g = Github(auth=auth)
    return g.get_repo(os.getenv("GITHUB_REPO"))


def run_git(args: list, cwd: str) -> dict:
    result = subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        cwd=cwd
    )
    return {
        "success": result.returncode == 0,
        "output": result.stdout.strip(),
        "error": result.stderr.strip()
    }


def git_commit(branch_name: str, files: list, message: str) -> dict:
    repo_path = os.getenv("REPO_LOCAL_PATH", ".")

    # Switch to the branch
    checkout = run_git(["checkout", branch_name], repo_path)
    if not checkout["success"]:
        # Try creating the branch locally if it doesn't exist
        run_git(["checkout", "-b", branch_name], repo_path)

    # Stage the files
    for filepath in files:
        run_git(["add", filepath], repo_path)

    # Commit
    commit = run_git(["commit", "-m", message], repo_path)

    if not commit["success"]:
        if "nothing to commit" in commit["output"] + commit["error"]:
            return {
                "success": True,
                "message": "Nothing new to commit — already up to date"
            }
        return {
            "success": False,
            "error": commit["error"]
        }

    return {
        "success": True,
        "message": f"Committed: {message}",
        "output": commit["output"]
    }


def push_branch(branch_name: str) -> dict:
    repo_path = os.getenv("REPO_LOCAL_PATH", ".")

    result = run_git(
        ["push", "origin", branch_name],
        repo_path
    )

    if result["success"]:
        return {
            "success": True,
            "branch": branch_name,
            "message": f"Branch '{branch_name}' pushed to origin"
        }

    return {
        "success": False,
        "branch": branch_name,
        "error": result["error"]
    }


def generate_pr_description(task: dict, changes: list) -> str:
    changes_text = "\n".join(f"- {c}" for c in changes)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": f"""Write a professional GitHub Pull Request description.

## Task
Title: {task['title']}
Description: {task['description']}

## Acceptance Criteria
{chr(10).join(f"- {c}" for c in task.get('acceptance_criteria', []))}

## Changes Made
{changes_text}

Write the PR description with these sections:
## Summary
## Changes Made
## Acceptance Criteria
## Testing
## Notes

Be concise and professional. Use markdown formatting."""
        }]
    )

    msg = response.content[0].text.strip()
    closes = f"Closes #{task['number']}"
    if closes not in msg:
        msg = f"{msg}\n\n{closes}"
    return msg


def _assign_reviewers(pr, config: dict) -> list[str]:
    """Request reviewers on a PR. Returns list of warnings (non-fatal)."""
    rev_cfg = (config or {}).get("reviewers", {})
    users = [u for u in rev_cfg.get("users", []) if u]
    teams = [t for t in rev_cfg.get("teams", []) if t]
    if not users and not teams:
        return []
    warnings = []
    try:
        with_github_retry(pr.create_review_request, reviewers=users, team_reviewers=teams)
    except Exception as exc:
        warnings.append(f"Reviewer assignment failed: {exc}")
    return warnings


def create_pull_request(
    task: dict,
    branch_name: str,
    base_branch: str,
    changes: list,
    config: dict = None,
) -> dict:
    try:
        repo = get_repo()

        pr_title = f"[Issue #{task['number']}] {task['title']}"
        pr_body = generate_pr_description(task, changes)

        pr = with_github_retry(
            repo.create_pull,
            title=pr_title,
            body=pr_body,
            head=branch_name,
            base=base_branch,
        )

        reviewer_warnings = _assign_reviewers(pr, config)

        return {
            "success": True,
            "pr_number": pr.number,
            "pr_url": pr.html_url,
            "title": pr_title,
            "message": f"PR #{pr.number} created successfully",
            "reviewer_warnings": reviewer_warnings,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def generate_commit_message(task: dict, changes: list) -> str:
    changes_text = "\n".join(f"- {c}" for c in changes)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{
            "role": "user",
            "content": f"""Write a concise git commit message for these changes.

Task: {task['title']}
Changes:
{changes_text}

Follow this format:
feat: short summary under 72 chars

- bullet point detail 1
- bullet point detail 2

Closes #{task['number']}

Return only the commit message, nothing else."""
        }]
    )

    msg = response.content[0].text.strip()
    closes = f"Closes #{task['number']}"
    if closes not in msg:
        msg = f"{msg}\n\n{closes}"
    return msg


if __name__ == "__main__":
    import argparse
    from agent.tools.task_reader import get_task, parse_task
    from rich import print

    parser = argparse.ArgumentParser(description="Generate a commit message and create a PR for an issue")
    parser.add_argument("--issue", type=int, required=True, help="GitHub issue number")
    parser.add_argument("--branch", required=True, help="Feature branch name")
    parser.add_argument("--base", default="main", help="Base branch (default: main)")
    args = parser.parse_args()

    raw = get_task(args.issue)
    task = parse_task(raw)
    print(f"Task: {task['title']}")

    commit_msg = generate_commit_message(task, [f"Implemented: {task['title']}"])
    print(f"\nCommit message:\n{commit_msg}")

    pr_result = create_pull_request(task, args.branch, args.base, [task["title"]])
    if pr_result["success"]:
        print(f"\nPR created: {pr_result['pr_url']}")
    else:
        print(f"\n[red]PR failed: {pr_result['error']}[/red]")