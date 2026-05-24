import os
import argparse
import anthropic
from dotenv import load_dotenv
from rich import print
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

load_dotenv("config/.env")

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Import all tools
from agent.tools.task_reader import get_task, parse_task, get_criteria
from agent.tools.branch_manager import validate_base, create_branch
from agent.tools.code_scanner import get_file_tree, list_files, read_file, search_code
from agent.tools.implementer import implement_task, apply_implementation, run_linter
from agent.tools.test_writer import generate_tests, write_test_file, run_tests
from agent.tools.reviewer import security_scan, optimize_code, check_seo, update_readme
from agent.tools.pr_creator import generate_commit_message, git_commit, push_branch, create_pull_request


def find_relevant_files(task: dict, repo_path: str) -> dict:
    """Ask Claude to identify which files are relevant to the task."""

    tree = get_file_tree(repo_path)

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": f"""You are a code analyst.
Given this task and file tree, identify the most relevant files to read.

## Task
Title: {task['title']}
Description: {task['description']}

## File Tree
{tree}

Return ONLY a JSON array of the most relevant file paths (max 5 files).
Pick files most likely to need changes or provide context.
Example: ["src/components/SearchBar.tsx", "src/hooks/useSearch.ts"]
Return only the JSON array, nothing else."""
        }]
    )

    raw = response.content[0].text.strip()

    # Parse file paths from response
    import json
    try:
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1])
        paths = json.loads(raw)
    except Exception:
        # Fallback — extract paths manually
        paths = []
        for line in raw.split("\n"):
            line = line.strip().strip('",[]')
            if line and ("/" in line or "\\" in line):
                paths.append(line)

    # Read each file
    file_contents = {}
    for relative_path in paths:
        full_path = os.path.join(repo_path, relative_path.lstrip("/"))
        result = read_file(full_path)
        if result["success"]:
            file_contents[relative_path] = result["content"]

    return file_contents


def run_agent(issue_number: int):
    repo_path = os.getenv("REPO_LOCAL_PATH", ".")
    base_branch = os.getenv("BASE_BRANCH", "main")
    branch_name = f"issue-{issue_number}"

    print(Panel(
        f"[bold]🤖 AI Coding Agent[/bold]\n"
        f"Issue    : #{issue_number}\n"
        f"Repo     : {os.getenv('GITHUB_REPO')}\n"
        f"Branch   : {branch_name}\n"
        f"Base     : {base_branch}",
        expand=False
    ))

    # ─────────────────────────────────────────
    # STAGE 1: Read the task
    # ─────────────────────────────────────────
    print("\n[bold cyan]━━ Stage 1: Reading task...[/bold cyan]")
    raw_task = get_task(issue_number)
    task = parse_task(raw_task)
    print(f"  ✅ Task    : {task['title']}")
    print(f"  ✅ Criteria: {len(task['acceptance_criteria'])} items")

    # ─────────────────────────────────────────
    # STAGE 2: Create branch
    # ─────────────────────────────────────────
    print("\n[bold cyan]━━ Stage 2: Creating branch...[/bold cyan]")
    validation = validate_base(base_branch)
    if not validation["valid"]:
        print(f"  [red]❌ Base branch error: {validation['message']}[/red]")
        return

    branch_result = create_branch(issue_number, base_branch)
    print(f"  ✅ {branch_result['message']}")

    # ─────────────────────────────────────────
    # STAGE 3: Scan the codebase
    # ─────────────────────────────────────────
    print("\n[bold cyan]━━ Stage 3: Scanning codebase...[/bold cyan]")
    file_contents = find_relevant_files(task, repo_path)
    print(f"  ✅ Found {len(file_contents)} relevant files:")
    for path in file_contents:
        print(f"     • {path}")

    if not file_contents:
        print("  [red]❌ No relevant files found[/red]")
        return

    # ─────────────────────────────────────────
    # STAGE 4: Implement the task
    # ─────────────────────────────────────────
    print("\n[bold cyan]━━ Stage 4: Implementing task...[/bold cyan]")
    impl = implement_task(task, file_contents)

    if not impl["success"]:
        print(f"  [red]❌ Implementation failed[/red]")
        return

    print(f"  ✅ File    : {impl['filepath']}")
    print(f"  ✅ Type    : {impl['change_type']}")
    print(f"  ✅ Plan    : {impl['explanation']}")

    apply_result = apply_implementation(impl)
    if apply_result["success"]:
        print(f"  ✅ Applied : {apply_result['message']}")
    else:
        print(f"  [red]❌ Apply failed: {apply_result.get('error')}[/red]")
        return

    # Track changed files for commit
    changed_files = []
    if impl["filepath"]:
        full_impl_path = os.path.join(
            repo_path, impl["filepath"].lstrip("/")
        )
        if os.path.isabs(impl["filepath"]):
            full_impl_path = impl["filepath"]
        changed_files.append(full_impl_path)

    # ─────────────────────────────────────────
    # STAGE 5: Write tests
    # ─────────────────────────────────────────
    print("\n[bold cyan]━━ Stage 5: Writing tests...[/bold cyan]")
    impl_filepath = changed_files[0] if changed_files else None

    if impl_filepath:
        file_data = read_file(impl_filepath)
        test_content = generate_tests(
            task,
            {impl_filepath: file_data["content"]}
        )

        # Save test file next to the component
        ext = os.path.splitext(impl_filepath)[1]
        test_filepath = impl_filepath.replace(ext, f".test{ext}")
        test_result = write_test_file(test_filepath, test_content)

        if test_result["success"]:
            print(f"  ✅ Tests written: {test_filepath}")
            changed_files.append(test_filepath)
        else:
            print(f"  [yellow]⚠️  Test write failed: {test_result.get('error')}[/yellow]")

    # ─────────────────────────────────────────
    # STAGE 6: Review
    # ─────────────────────────────────────────
    print("\n[bold cyan]━━ Stage 6: Reviewing...[/bold cyan]")

    if impl_filepath:
        # Security
        sec = security_scan(impl_filepath)
        sec_issues = "no issues" if "no" in sec["output"].lower() else "issues found"
        print(f"  ✅ Security : {sec_issues}")

        # Optimisation
        opt = optimize_code(impl_filepath)
        if opt.get("updated_code"):
            with open(impl_filepath, "w", encoding="utf-8") as f:
                f.write(opt["updated_code"])
            print(f"  ✅ Optimised: code updated")
        else:
            print(f"  ✅ Optimised: no changes needed")

        # SEO
        seo = check_seo(impl_filepath)
        print(f"  ✅ SEO      : {len(seo.get('issues', []))} issues found")

    # README
    readme_result = update_readme(repo_path, impl["explanation"])
    if readme_result["success"]:
        print(f"  ✅ README   : updated")
        readme_path = os.path.join(repo_path, "README.md")
        if readme_path not in changed_files:
            changed_files.append(readme_path)

    # ─────────────────────────────────────────
    # STAGE 7: Commit, push and raise PR
    # ─────────────────────────────────────────
    print("\n[bold cyan]━━ Stage 7: Creating PR...[/bold cyan]")

    changes_summary = [
        impl["explanation"],
        f"Added test file for {os.path.basename(impl_filepath or '')}",
        "Updated README with recent changes"
    ]

    commit_msg = generate_commit_message(task, changes_summary)
    print(f"  ✅ Commit message generated")

    commit_result = git_commit(branch_name, changed_files, commit_msg)
    print(f"  ✅ Committed: {commit_result['message'][:60]}")

    push_result = push_branch(branch_name)
    if not push_result["success"]:
        print(f"  [red]❌ Push failed: {push_result['error']}[/red]")
        return

    print(f"  ✅ Pushed   : branch {branch_name}")

    pr_result = create_pull_request(
        task,
        branch_name,
        base_branch,
        changes_summary
    )

    if pr_result["success"]:
        print(f"  ✅ PR #{pr_result['pr_number']} created")
    else:
        print(f"  [red]❌ PR failed: {pr_result['error']}[/red]")
        return

    # ─────────────────────────────────────────
    # DONE
    # ─────────────────────────────────────────
    print(Panel(
        f"[bold green]🎉 Agent completed successfully![/bold green]\n\n"
        f"Issue  : #{issue_number} — {task['title']}\n"
        f"Branch : {branch_name}\n"
        f"PR     : {pr_result['pr_url']}",
        expand=False
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="AI Coding Agent"
    )
    parser.add_argument(
        "--issue",
        type=int,
        required=True,
        help="GitHub issue number to implement"
    )
    args = parser.parse_args()
    run_agent(args.issue)