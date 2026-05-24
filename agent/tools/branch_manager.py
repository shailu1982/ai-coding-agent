import os
from github import Github, Auth
from dotenv import load_dotenv
from agent.utils.retry import with_github_retry

load_dotenv("config/.env")


def get_repo():
    auth = Auth.Token(os.getenv("GITHUB_TOKEN"))
    g = Github(auth=auth)
    return with_github_retry(g.get_repo, os.getenv("GITHUB_REPO"))


def validate_base(base_branch: str = "main") -> dict:
    repo = get_repo()
    branches = [b.name for b in repo.get_branches()]

    if base_branch in branches:
        return {
            "valid": True,
            "branch": base_branch,
            "message": f"Base branch '{base_branch}' exists"
        }

    return {
        "valid": False,
        "branch": base_branch,
        "message": f"Base branch '{base_branch}' not found. Available: {branches}"
    }


def create_branch(issue_number: int, base_branch: str = "main") -> dict:
    repo = get_repo()
    branch_name = f"issue-{issue_number}"

    # Check if branch already exists
    existing = [b.name for b in repo.get_branches()]
    if branch_name in existing:
        return {
            "success": True,
            "branch": branch_name,
            "message": f"Branch '{branch_name}' already exists"
        }

    # Get the SHA of the base branch
    base = repo.get_branch(base_branch)
    sha = base.commit.sha

    # Create the new branch
    with_github_retry(
        repo.create_git_ref,
        ref=f"refs/heads/{branch_name}",
        sha=sha,
    )

    return {
        "success": True,
        "branch": branch_name,
        "base": base_branch,
        "sha": sha,
        "message": f"Branch '{branch_name}' created from '{base_branch}'"
    }


def checkout(branch_name: str) -> dict:
    import subprocess
    result = subprocess.run(
        ["git", "checkout", branch_name],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        return {
            "success": True,
            "branch": branch_name,
            "message": f"Switched to branch '{branch_name}'"
        }

    return {
        "success": False,
        "branch": branch_name,
        "message": result.stderr.strip()
    }


if __name__ == "__main__":
    import argparse
    from rich import print

    parser = argparse.ArgumentParser(description="Create a branch for a GitHub issue")
    parser.add_argument("--issue", type=int, required=True, help="GitHub issue number")
    parser.add_argument("--base", default="main", help="Base branch (default: main)")
    args = parser.parse_args()

    validation = validate_base(args.base)
    print(validation)

    if validation["valid"]:
        result = create_branch(args.issue, args.base)
        print(result)