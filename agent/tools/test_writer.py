import os
import sys
import subprocess

from agent.utils.client import get_client
from agent.utils.parsing import strip_code_fences, parse_test_counts

_NPX = "npx.cmd" if sys.platform == "win32" else "npx"


def _detect_framework(file_contents: dict) -> str:
    """Return 'react', 'jest', 'pytest', or 'generic' based on file extensions."""
    for filepath in file_contents:
        ext = os.path.splitext(filepath)[1]
        if ext in (".tsx", ".jsx"):
            return "react"
        if ext in (".ts", ".js"):
            return "jest"
        if ext == ".py":
            return "pytest"
    return "generic"


def write_test_file(filepath: str, content: str) -> dict:
    try:
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return {"success": True, "filepath": filepath}
    except Exception as e:
        return {"success": False, "filepath": filepath, "error": str(e)}


def run_tests(test_path: str) -> dict:
    repo_path = os.getenv("REPO_LOCAL_PATH", ".")
    ext = os.path.splitext(test_path)[1]

    if ext == ".py":
        cmd = [sys.executable, "-m", "pytest", test_path, "-v"]
    else:
        cmd = [_NPX, "jest", test_path, "--no-coverage", "--watchAll=false"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=repo_path,
            timeout=60
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "test_path": test_path,
            "passed_count": 0,
            "failed_count": 0,
            "output": "Tests timed out after 60 seconds"
        }

    output = result.stdout + result.stderr

    ext = os.path.splitext(test_path)[1]
    runner = "pytest" if ext == ".py" else "jest"
    passed_count, failed_count = parse_test_counts(output, runner)

    return {
        "success": result.returncode == 0,
        "test_path": test_path,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "output": output
    }


def get_coverage(module_path: str) -> dict:
    repo_path = os.getenv("REPO_LOCAL_PATH", ".")

    result = subprocess.run(
        [_NPX, "jest", module_path, "--coverage", "--watchAll=false", "--coverageReporters=text"],
        capture_output=True,
        text=True,
        cwd=repo_path
    )

    output = result.stdout + result.stderr
    coverage = None

    for line in output.split("\n"):
        if "All files" in line or "%" in line:
            parts = line.split("|")
            if len(parts) > 1:
                try:
                    coverage = float(parts[1].strip().rstrip("%"))
                    break
                except ValueError:
                    pass

    return {
        "success": result.returncode == 0,
        "module_path": module_path,
        "coverage_percent": coverage,
        "output": output
    }


def generate_tests(task: dict, file_contents: dict) -> str:
    framework = _detect_framework(file_contents)

    files_context = ""
    for filepath, content in file_contents.items():
        files_context += f"\n\n--- FILE: {filepath} ---\n{content}"

    criteria = "\n".join(f"- {c}" for c in task.get("acceptance_criteria", []))

    if framework == "react":
        role = "an expert React and TypeScript test engineer"
        instructions = """\
1. Use Jest and React Testing Library
2. Use @testing-library/jest-dom matchers
3. Mock external dependencies and API calls
4. Return a raw TypeScript test file ready to save as .test.tsx"""
    elif framework == "jest":
        role = "an expert TypeScript/JavaScript test engineer"
        instructions = """\
1. Use Jest for all tests
2. Mock external dependencies and modules
3. Return a raw TypeScript test file ready to save as .test.ts"""
    elif framework == "pytest":
        role = "an expert Python test engineer"
        instructions = """\
1. Use pytest for all tests
2. Use fixtures for shared setup
3. Return a raw Python test file ready to save as test_*.py"""
    else:
        role = "an expert software test engineer"
        instructions = """\
1. Write tests appropriate for the language and framework in the provided code
2. Mock external dependencies
3. Return only the raw test file content"""

    prompt = f"""You are {role}.

Write comprehensive tests for the following task.

## Task
{task['title']}

## Acceptance Criteria
{criteria}

## Code to Test
{files_context}

## Instructions
{instructions}
5. Write a test for every acceptance criterion
6. Cover key edge cases
7. Give each test a clear descriptive name
8. Group related tests in describe blocks

Return ONLY the raw test file content — no explanation, no markdown fences."""

    response = get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()
    raw = strip_code_fences(raw)

    return raw


if __name__ == "__main__":
    import argparse
    from agent.tools.task_reader import get_task, parse_task
    from agent.tools.code_scanner import read_file
    from rich import print

    parser = argparse.ArgumentParser(description="Generate and run tests for a GitHub issue")
    parser.add_argument("--issue", type=int, required=True, help="GitHub issue number")
    parser.add_argument("--file", required=True, help="Implementation file to write tests for")
    args = parser.parse_args()

    raw = get_task(args.issue)
    task = parse_task(raw)
    print(f"Task: {task['title']}")

    file_data = read_file(args.file)
    if not file_data["success"]:
        print(f"[red]File not found: {args.file}[/red]")
        raise SystemExit(1)

    test_content = generate_tests(task, {args.file: file_data["content"]})

    ext = os.path.splitext(args.file)[1]
    test_filepath = args.file.replace(ext, f".test{ext}")
    result = write_test_file(test_filepath, test_content)
    print(result)

    test_result = run_tests(test_filepath)
    print(f"Passed: {test_result['passed_count']}  Failed: {test_result['failed_count']}")
    if not test_result["success"]:
        print(test_result["output"][:500])
