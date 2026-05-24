import os
import subprocess
import anthropic
from dotenv import load_dotenv

load_dotenv("config/.env")

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def write_test_file(filepath: str, content: str) -> dict:
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return {
            "success": True,
            "filepath": filepath,
            "message": f"Test file written successfully"
        }
    except Exception as e:
        return {
            "success": False,
            "filepath": filepath,
            "error": str(e)
        }


def run_tests(test_path: str) -> dict:
    repo_path = os.getenv("REPO_LOCAL_PATH", ".")

    try:
        result = subprocess.run(
            ["npx.cmd", "jest", test_path, "--no-coverage", "--watchAll=false"],
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

    passed = result.returncode == 0
    output = result.stdout + result.stderr

    # Count passed and failed
    passed_count = output.count("✓") + output.count("√") + output.count("PASS")
    failed_count = output.count("✗") + output.count("×") + output.count("FAIL")

    return {
        "success": passed,
        "test_path": test_path,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "output": output
    }


def get_coverage(module_path: str) -> dict:
    repo_path = os.getenv("REPO_LOCAL_PATH", ".")

    result = subprocess.run(
        [
            "npx.cmd", "jest",
            module_path,
            "--coverage",
            "--watchAll=false",
            "--coverageReporters=text"
        ],
        capture_output=True,
        text=True,
        cwd=repo_path
    )

    output = result.stdout + result.stderr

    # Extract coverage percentage
    coverage = None
    for line in output.split("\n"):
        if "All files" in line or "SearchBar" in line:
            parts = line.split("|")
            if len(parts) > 1:
                try:
                    coverage = float(parts[1].strip())
                except ValueError:
                    pass

    return {
        "success": result.returncode == 0,
        "module_path": module_path,
        "coverage_percent": coverage,
        "output": output
    }


def generate_tests(task: dict, file_contents: dict) -> str:
    files_context = ""
    for filepath, content in file_contents.items():
        files_context += f"\n\n--- FILE: {filepath} ---\n{content}"

    criteria = "\n".join(
        f"- {c}" for c in task.get("acceptance_criteria", [])
    )

    prompt = f"""You are an expert React and TypeScript test engineer.

Your job is to write comprehensive Jest and React Testing Library tests
for the following task.

## Task
Title: {task['title']}

## Acceptance Criteria
{criteria}

## Updated Code
{files_context}

## Instructions
1. Write tests for ALL acceptance criteria
2. Write tests for edge cases too
3. Use React Testing Library best practices
4. Use @testing-library/jest-dom matchers
5. Mock any external dependencies
6. Each test must have a clear descriptive name
7. Group related tests inside describe blocks

Return ONLY the raw TypeScript test file content.
No explanation, no markdown fences, just the code.
The file should be ready to save and run immediately."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()

    # Strip markdown fences if Claude added them
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1])

    return raw


# Quick test
if __name__ == "__main__":
    from rich import print
    from agent.tools.task_reader import get_task, parse_task
    from agent.tools.code_scanner import read_file, search_code

    repo_path = os.getenv("REPO_LOCAL_PATH", ".")

    print("\n[bold]Step 1: Loading task #18...[/bold]")
    raw = get_task(18)
    task = parse_task(raw)
    print(f"Task: {task['title']}")

    print("\n[bold]Step 2: Finding SearchBar.tsx...[/bold]")
    results = search_code("SearchBar", repo_path)
    target_file = None
    for r in results:
        if "SearchBar.tsx" in r["filepath"] and "test" not in r["filepath"]:
            target_file = r["filepath"]
            break

    if not target_file:
        print("[red]SearchBar.tsx not found![/red]")
        exit()

    print(f"Found: {target_file}")

    print("\n[bold]Step 3: Reading updated file...[/bold]")
    file_data = read_file(target_file)
    print(f"Lines: {file_data['line_count']}")

    print("\n[bold]Step 4: Asking Claude to write tests...[/bold]")
    test_content = generate_tests(
        task,
        {target_file: file_data["content"]}
    )

    # Save test file next to the component
    test_filepath = target_file.replace(".tsx", ".test.tsx")
    print(f"\n[bold]Step 5: Saving test file to:[/bold] {test_filepath}")
    result = write_test_file(test_filepath, test_content)
    print(result)

    print("\n[bold]Step 6: Running tests...[/bold]")
    test_result = run_tests(test_filepath)
    print(f"Passed : {test_result['passed_count']}")
    print(f"Failed : {test_result['failed_count']}")
    print(f"Output :\n{test_result['output'][:500]}")