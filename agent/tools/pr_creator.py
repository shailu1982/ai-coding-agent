import os
import subprocess
import anthropic
from github import Github, Auth
from dotenv import load_dotenv

load_dotenv("config/.env")

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


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

    return response.content[0].text.strip()


def create_pull_request(
    task: dict,
    branch_name: str,
    base_branch: str,
    changes: list
) -> dict:
    try:
        repo = get_repo()

        # Generate PR title
        pr_title = f"[Issue #{task['number']}] {task['title']}"

        # Generate PR description
        pr_body = generate_pr_description(task, changes)

        # Create the PR
        pr = repo.create_pull(
            title=pr_title,
            body=pr_body,
            head=branch_name,
            base=base_branch
        )

        return {
            "success": True,
            "pr_number": pr.number,
            "pr_url": pr.html_url,
            "title": pr_title,
            "message": f"PR #{pr.number} created successfully"
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

    return response.content[0].text.strip()


# Quick test
if __name__ == "__main__":
    from rich import print
    from agent.tools.task_reader import get_task, parse_task

    print("\n[bold]Step 1: Loading task #18...[/bold]")
    raw = get_task(18)
    task = parse_task(raw)
    print(f"Task: {task['title']}")

    changes = [
        "Added result count Typography label above search results list",
        "Label shows '{count} results for {query}' when results exist",
        "Label only renders when results.length > 0 and query is non-empty",
        "Added SearchBar.test.tsx with full test coverage",
        "Updated README with recent changes"
    ]

    print("\n[bold]Step 2: Generating commit message...[/bold]")
    commit_msg = generate_commit_message(task, changes)
    print(commit_msg)

    print("\n[bold]Step 3: Committing files...[/bold]")
    repo_path = os.getenv("REPO_LOCAL_PATH", ".")
    result = git_commit(
        "issue-18",
        [
            os.path.join(repo_path, "src", "components", "SearchBar.tsx"),
            os.path.join(repo_path, "src", "components", "SearchBar.test.tsx"),
            os.path.join(repo_path, "README.md")
        ],
        commit_msg
    )
    print(result)

    print("\n[bold]Step 4: Pushing branch...[/bold]")
    push_result = push_branch("issue-18")
    print(push_result)

    print("\n[bold]Step 5: Creating Pull Request...[/bold]")
    pr_result = create_pull_request(
        task,
        "issue-18",
        "main",
        changes
    )
    print(pr_result)

    if pr_result["success"]:
        print(f"\n[bold green]🎉 PR created![/bold green]")
        print(f"[bold]URL:[/bold] {pr_result['pr_url']}")