import os
import json
import argparse
from dotenv import load_dotenv
from rich import print
from rich.panel import Panel
from agent.utils.client import get_client
from agent.utils.config import load_repo_config
from agent.utils.parsing import strip_code_fences

load_dotenv("config/.env")

client = get_client()

from agent.tools.task_reader import get_task, parse_task
from agent.tools.branch_manager import validate_base, create_branch
from agent.tools.code_scanner import get_file_tree, read_file
from agent.tools.implementer import implement_task, apply_changes, run_linter
from agent.tools.test_writer import generate_tests, write_test_file, run_tests
from agent.tools.healer import fix_failing_tests, is_runner_error
from agent.tools.regression_guard import capture_baseline, check_regressions
from agent.tools.type_checker import run_type_check
from agent.tools.reviewer import security_scan, optimize_code, check_seo, update_readme
from agent.tools.pr_creator import generate_commit_message, git_commit, push_branch, create_pull_request
from agent.utils.examples import find_examples, save_example


def _primary_file(filepaths: list) -> str:
    """Return the best file to anchor test generation — avoids barrel/type files."""
    secondary = ("index.", "types.", "constants.", "interfaces.", "exports.")
    for f in filepaths:
        if not any(os.path.basename(f).lower().startswith(p) for p in secondary):
            return f
    return filepaths[0]


def _resolve(filepath: str, repo_path: str) -> str:
    if os.path.isabs(filepath):
        return filepath
    return os.path.join(repo_path, filepath.lstrip("/\\"))


def find_relevant_files(task: dict, repo_path: str, max_files: int = 5) -> dict:
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

Return ONLY a JSON array of the most relevant file paths (max {max_files} files).
Pick files most likely to need changes or provide context.
Example: ["src/components/MyComponent.tsx", "src/utils/helpers.ts"]
Return only the JSON array, nothing else."""
        }]
    )

    raw = response.content[0].text.strip()

    try:
        if raw.startswith("```"):
            raw = strip_code_fences(raw)
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


def run_agent(issue_number: int) -> str:
    """Run the full pipeline for a GitHub issue. Returns the PR URL on success."""
    repo_path = os.getenv("REPO_LOCAL_PATH", ".")
    config = load_repo_config(repo_path)

    base_branch = config["base_branch"]
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
        raise RuntimeError(f"Base branch error: {validation['message']}")

    branch_result = create_branch(issue_number, base_branch)
    if not branch_result.get("success"):
        raise RuntimeError(f"Branch creation failed: {branch_result.get('message')}")
    print(f"  ✅ {branch_result['message']}")

    # ─────────────────────────────────────────
    # STAGE 3: Scan the codebase + capture baseline
    # ─────────────────────────────────────────
    print("\n[bold cyan]━━ Stage 3: Scanning codebase...[/bold cyan]")
    file_contents = find_relevant_files(task, repo_path, max_files=config["max_relevant_files"])
    print(f"  ✅ Found {len(file_contents)} relevant files:")
    for path in file_contents:
        print(f"     • {path}")

    # Capture test baseline before touching any files
    guard_enabled = config["regression_guard"]
    baseline = None

    if not file_contents:
        raise RuntimeError("No relevant files found in codebase")

    if guard_enabled:
        baseline = capture_baseline(repo_path, config)
        if baseline.get("skipped"):
            print(f"  ℹ️  Baseline : skipped ({baseline['output'][:80]})")
        else:
            print(f"  ✅ Baseline : {baseline['passed']} passed, {baseline['failed']} failed ({baseline['runner']})")

    # ─────────────────────────────────────────
    # STAGE 4: Implement the task (multi-file)
    # ─────────────────────────────────────────
    print("\n[bold cyan]━━ Stage 4: Implementing task...[/bold cyan]")
    examples = find_examples(task)
    if examples:
        print(f"  ✅ Examples : {len(examples)} similar past task(s) loaded as few-shot context")
    impl = implement_task(task, file_contents, examples=examples)

    if not impl["success"]:
        raise RuntimeError(f"Implementation step failed: {impl.get('explanation')}")

    print(f"  ✅ Changes  : {len(impl['changes'])} file(s) planned")

    apply_results = apply_changes(impl["changes"])

    changed_files = []
    failed_paths = []

    for change, result in zip(impl["changes"], apply_results):
        icon = "✅" if result["success"] else "✗"
        label = change["change_type"].upper()
        detail = result.get("message") or result.get("error", "")
        print(f"  {icon} [{label}] {change['filepath']} — {detail}")

        if result["success"]:
            changed_files.append(_resolve(change["filepath"], repo_path))
        else:
            failed_paths.append(change["filepath"])

    if not changed_files:
        raise RuntimeError(f"All {len(impl['changes'])} change(s) failed to apply")

    if failed_paths:
        print(f"  [yellow]⚠️  {len(failed_paths)} change(s) failed — continuing with {len(changed_files)} succeeded[/yellow]")

    # Linter on every successfully changed file (non-blocking)
    for path in changed_files:
        lint = run_linter(path)
        if lint.get("output"):
            print(f"  ⚠️  Linter  : {os.path.basename(path)}: {lint['output'][:100]}")

    # ─────────────────────────────────────────
    # STAGE 4b: Type checking
    # ─────────────────────────────────────────
    print("\n[bold cyan]━━ Stage 4b: Type checking...[/bold cyan]")
    tc = run_type_check(repo_path, config)
    if tc["skipped"]:
        print(f"  ℹ️  Skipped  : {tc['output'][:80]}")
    elif tc["success"]:
        print(f"  ✅ {tc['checker']}    : no type errors")
    else:
        snippet = tc["output"][-600:].strip()
        print(f"  [yellow]⚠️  {tc['checker']}    : {tc['errors']} error(s)[/yellow]")
        print(f"  [dim]{snippet[:300]}[/dim]")
        if config.get("type_check", {}).get("blocking", False):
            raise RuntimeError(
                f"Type check failed ({tc['errors']} error(s) in {tc['checker']}).\n\n{snippet}"
            )

    # ─────────────────────────────────────────
    # STAGE 5: Write tests + self-healing loop
    # ─────────────────────────────────────────
    print("\n[bold cyan]━━ Stage 5: Writing tests...[/bold cyan]")
    impl_filepath = _primary_file(changed_files)
    max_heal = config["max_heal_attempts"]

    # Build context from all changed files so tests understand the full picture
    file_context = {}
    for path in changed_files:
        data = read_file(path)
        if data["success"]:
            file_context[path] = data["content"]

    if not file_context:
        print(f"  [yellow]⚠️  Could not read any changed files — skipping tests[/yellow]")
    else:
        test_content = generate_tests(task, file_context)
        base, ext = os.path.splitext(impl_filepath)
        test_filepath = f"{base}.test{ext}"
        write_result = write_test_file(test_filepath, test_content)

        if not write_result["success"]:
            print(f"  [yellow]⚠️  Test write failed: {write_result.get('error')}[/yellow]")
        else:
            print(f"  ✅ Tests    : {os.path.basename(test_filepath)}")
            changed_files.append(test_filepath)

            # Run tests and heal if they fail
            run_result = run_tests(test_filepath)

            if run_result["success"]:
                print(f"  ✅ Passed   : {run_result['passed_count']} test(s)")

            elif is_runner_error(run_result["output"]):
                print(f"  [yellow]⚠️  Test runner unavailable — skipping[/yellow]")

            else:
                print(f"  [yellow]⚠️  {run_result['failed_count']} test(s) failing — starting heal loop[/yellow]")

                healed = False
                for attempt in range(1, max_heal + 1):
                    print(f"\n  [bold]Heal attempt {attempt}/{max_heal}[/bold]")

                    heal = fix_failing_tests(
                        impl_filepath, test_filepath, run_result["output"], attempt
                    )

                    if not heal["success"]:
                        print(f"  [red]✗ Healer error: {heal.get('error')}[/red]")
                        break

                    target = os.path.basename(heal["filepath"])
                    print(f"  → Fixed {heal['fix_target']} ({target}): {heal['explanation']}")

                    run_result = run_tests(test_filepath)

                    if run_result["success"]:
                        print(f"  ✅ Healed   : {run_result['passed_count']} test(s) now passing")
                        healed = True
                        break
                    else:
                        print(f"  [yellow]  Still {run_result['failed_count']} failing[/yellow]")

                if not healed:
                    print(f"\n  [yellow]⚠️  Tests still failing after {max_heal} attempt(s) — continuing[/yellow]")

    # ─────────────────────────────────────────
    # STAGE 6: Regression guard
    # ─────────────────────────────────────────
    print("\n[bold cyan]━━ Stage 6: Regression guard...[/bold cyan]")
    # Count test files the agent generated — failures in these don't count
    # as regressions against pre-existing code (env config issues, etc.)
    new_test_files = [f for f in changed_files if ".test." in os.path.basename(f)]
    if guard_enabled and baseline is not None:
        reg = check_regressions(repo_path, baseline, config, grace_suites=len(new_test_files))
        if reg.get("skipped"):
            print(f"  ℹ️  Skipped  : {reg.get('snippet', 'no runner available')[:80]}")
        elif reg["regressions"] == 0:
            delta = reg["after_passed"] - reg["baseline_passed"]
            delta_str = f"+{delta}" if delta >= 0 else str(delta)
            print(f"  ✅ Clean    : {reg['after_failed']} failing (baseline {reg['baseline_failed']}), {delta_str} passing")
        else:
            snippet = reg["snippet"]
            raise RuntimeError(
                f"Regression detected: {reg['regressions']} new test failure(s) introduced "
                f"({reg['baseline_failed']} → {reg['after_failed']} failing).\n\n{snippet}"
            )
    else:
        print(f"  ℹ️  Skipped  : REGRESSION_GUARD=false")

    # ─────────────────────────────────────────
    # STAGE 7: Review
    # ─────────────────────────────────────────
    print("\n[bold cyan]━━ Stage 7: Reviewing...[/bold cyan]")
    review_cfg = config.get("review", {})

    # Security
    if review_cfg.get("security", True):
        for review_path in changed_files:
            sec = security_scan(review_path)
            output_text = sec.get("output", "")
            # Parse the structured ISSUES_FOUND field rather than substring matching
            issues_found = False
            for sec_line in output_text.split("\n"):
                if sec_line.strip().upper().startswith("ISSUES_FOUND:"):
                    issues_found = "yes" in sec_line.lower()
                    break
            sec_status = "issues found — review output" if issues_found else "clean"
            print(f"  ✅ Security : {os.path.basename(review_path)} — {sec_status}")
    else:
        print(f"  ℹ️  Security : skipped (config)")

    # Optimisation
    if review_cfg.get("optimize", True):
        for review_path in changed_files:
            opt = optimize_code(review_path)
            if opt.get("updated_code"):
                updated = opt["updated_code"]
                # Safety check: don't overwrite if the optimized code is drastically shorter
                try:
                    with open(review_path, "r", encoding="utf-8") as f:
                        original = f.read()
                    if len(updated) < len(original) * 0.5:
                        print(f"  ⚠️  Optimised: {os.path.basename(review_path)} — skipped (output too short, likely truncated)")
                        continue
                    with open(review_path, "w", encoding="utf-8") as f:
                        f.write(updated)
                    print(f"  ✅ Optimised: {os.path.basename(review_path)} — code updated")
                except Exception as opt_err:
                    print(f"  ⚠️  Optimised: {os.path.basename(review_path)} — write failed: {opt_err}")
            else:
                print(f"  ✅ Optimised: {os.path.basename(review_path)} — no changes needed")
    else:
        print(f"  ℹ️  Optimise : skipped (config)")

    # SEO / accessibility (only applies to UI files)
    if review_cfg.get("seo", True):
        seo = check_seo(impl_filepath)
        seo_issues = seo.get("issues", [])
        seo_msg = f"{len(seo_issues)} issue(s) found" if seo_issues else "clean"
        print(f"  ✅ SEO/a11y : {seo_msg}")
    else:
        print(f"  ℹ️  SEO/a11y : skipped (config)")

    # README
    if review_cfg.get("readme", True):
        readme_result = update_readme(repo_path, impl["explanation"])
        if readme_result["success"]:
            print(f"  ✅ README   : updated")
            readme_path = os.path.join(repo_path, "README.md")
            if readme_path not in changed_files:
                changed_files.append(readme_path)
    else:
        print(f"  ℹ️  README   : skipped (config)")

    # ─────────────────────────────────────────
    # STAGE 8: Commit, push and raise PR
    # ─────────────────────────────────────────
    print("\n[bold cyan]━━ Stage 8: Creating PR...[/bold cyan]")

    test_files = [f for f in changed_files if ".test." in os.path.basename(f)]
    changes_summary = [c["explanation"] for c in impl["changes"] if c.get("explanation")]
    if test_files:
        changes_summary.append(f"Added tests for {os.path.basename(impl_filepath)}")
    changes_summary.append("Updated README")

    commit_msg = generate_commit_message(task, changes_summary)
    print(f"  ✅ Commit   : message generated")

    commit_result = git_commit(branch_name, changed_files, commit_msg)
    print(f"  ✅ Committed: {commit_result['message'][:60]}")

    push_result = push_branch(branch_name)
    if not push_result["success"]:
        raise RuntimeError(f"Push failed: {push_result['error']}")

    print(f"  ✅ Pushed   : branch {branch_name}")

    pr_result = create_pull_request(
        task,
        branch_name,
        base_branch,
        changes_summary,
        config=config,
    )

    if not pr_result["success"]:
        raise RuntimeError(f"PR creation failed: {pr_result['error']}")

    print(f"  ✅ PR #{pr_result['pr_number']} created")

    for warn in pr_result.get("reviewer_warnings", []):
        print(f"  [yellow]⚠️  {warn}[/yellow]")

    try:
        save_example(task, impl["changes"], pr_result["pr_url"])
        print(f"  ✅ Saved    : implementation added to examples store")
    except Exception as ex_err:
        print(f"  [yellow]⚠️  Examples store: {ex_err}[/yellow]")

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

    return pr_result["pr_url"]


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