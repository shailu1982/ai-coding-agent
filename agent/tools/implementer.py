import os
import re
from dotenv import load_dotenv
from agent.utils.retry import RetryingClient

load_dotenv("config/.env")

client = RetryingClient(api_key=os.getenv("ANTHROPIC_API_KEY"))


def write_file(filepath: str, content: str) -> dict:
    try:
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return {"success": True, "filepath": filepath, "message": "File written successfully"}
    except Exception as e:
        return {"success": False, "filepath": filepath, "error": str(e)}


def edit_file(filepath: str, old_str: str, new_str: str) -> dict:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        if old_str not in content:
            return {
                "success": False,
                "filepath": filepath,
                "error": "Could not find the exact string to replace"
            }

        updated = content.replace(old_str, new_str, 1)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(updated)

        return {"success": True, "filepath": filepath, "message": "File edited successfully"}

    except FileNotFoundError:
        return {"success": False, "filepath": filepath, "error": "File not found"}
    except Exception as e:
        return {"success": False, "filepath": filepath, "error": str(e)}


def delete_file(filepath: str) -> dict:
    try:
        os.remove(filepath)
        return {"success": True, "filepath": filepath, "message": "File deleted successfully"}
    except Exception as e:
        return {"success": False, "filepath": filepath, "error": str(e)}


def run_linter(filepath: str) -> dict:
    import subprocess
    import sys

    ext = os.path.splitext(filepath)[1]
    npx = "npx.cmd" if sys.platform == "win32" else "npx"

    if ext in (".ts", ".tsx", ".js", ".jsx"):
        cmd = [npx, "eslint", filepath, "--format", "compact"]
    elif ext == ".py":
        cmd = ["flake8", filepath]
    else:
        return {"success": True, "filepath": filepath, "output": "No linter configured for this file type"}

    result = subprocess.run(cmd, capture_output=True, text=True)
    return {
        "success": result.returncode == 0,
        "filepath": filepath,
        "output": (result.stdout + result.stderr).strip()
    }


def _parse_changes(raw: str) -> list:
    """
    Parse a multi-change response into a list of change dicts.
    Supports both the multi-change format (CHANGE 1: ... CHANGE 2: ...) and
    the legacy single-change format for backward compatibility.
    """
    # Split on "CHANGE N:" markers
    chunks = re.split(r'\nCHANGE\s+\d+\s*:', raw, flags=re.IGNORECASE)

    # No markers found — treat whole response as a single change
    if len(chunks) == 1:
        chunks = [raw]
    else:
        chunks = chunks[1:]  # discard the preamble before CHANGE 1:

    changes = []

    for chunk in chunks:
        if not chunk.strip():
            continue

        change = {
            "filepath": None,
            "change_type": None,
            "old_code": "",
            "new_code": None,
            "explanation": None,
        }

        for line in chunk.split("\n"):
            stripped = line.strip()
            if stripped.startswith("FILEPATH:"):
                change["filepath"] = stripped.replace("FILEPATH:", "").strip().strip("`")
            elif stripped.startswith("CHANGE_TYPE:"):
                change["change_type"] = stripped.replace("CHANGE_TYPE:", "").strip().lower()
            elif stripped.startswith("EXPLANATION:"):
                change["explanation"] = stripped.replace("EXPLANATION:", "").strip()

        # Extract multi-line OLD_CODE and NEW_CODE by position
        if "NEW_CODE:" in chunk:
            new_marker = chunk.find("NEW_CODE:")
            expl_marker = chunk.find("EXPLANATION:")

            if "OLD_CODE:" in chunk:
                old_marker = chunk.find("OLD_CODE:") + len("OLD_CODE:")
                change["old_code"] = chunk[old_marker:new_marker].strip()

            code_start = new_marker + len("NEW_CODE:")
            code_end = expl_marker if expl_marker > new_marker else None
            change["new_code"] = chunk[code_start:code_end].strip() if code_end else chunk[code_start:].strip()

        if change["filepath"] and change["change_type"] and change["new_code"]:
            changes.append(change)

    return changes


def _format_examples(examples: list) -> str:
    if not examples:
        return ""
    lines = ["\n## Past Examples From This Codebase\n"]
    for i, ex in enumerate(examples, 1):
        lines.append(f"### Example {i}: {ex['title']}")
        for c in ex.get("changes", []):
            lines.append(f"- {c['filepath']} ({c['change_type']}): {c['explanation']}")
        lines.append("")
    return "\n".join(lines)


def implement_task(task: dict, file_contents: dict, examples: list = None) -> dict:
    """
    Ask Claude to produce all code changes needed to satisfy the task.
    Returns {"success", "changes": [...], "explanation"}.
    """
    files_context = ""
    for filepath, content in file_contents.items():
        files_context += f"\n\n--- FILE: {filepath} ---\n{content}"

    criteria = "\n".join(f"- {c}" for c in task.get("acceptance_criteria", []))
    examples_section = _format_examples(examples or [])

    prompt = f"""You are an expert software engineer.
Your job is to implement the following task completely and correctly.

## Task
Title: {task['title']}

## Description
{task['description']}

## Acceptance Criteria
{criteria}
{examples_section}
## Current Code
{files_context}

## Instructions
1. Analyse the current code carefully
2. Identify EVERY file that must change to fully satisfy all acceptance criteria
   — include barrel exports, type files, route registrations, imports, etc.
3. Make the minimal change per file — do not touch anything unrelated
4. Preserve existing code style, formatting, and import conventions
5. Return ALL changes using this exact format, one block per file:

CHANGE 1:
FILEPATH: <file path>
CHANGE_TYPE: <edit or create>
OLD_CODE:
<exact existing block to replace — omit section for create>
NEW_CODE:
<replacement or new content>
EXPLANATION: <one sentence>

CHANGE 2:
FILEPATH: <file path>
...

Return as many CHANGE blocks as needed. Be precise and complete."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8096,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text
    changes = _parse_changes(raw)

    if not changes:
        return {"success": False, "changes": [], "explanation": "Could not parse any changes from response"}

    # Top-level explanation — join all individual explanations
    explanation = "; ".join(c["explanation"] for c in changes if c.get("explanation"))

    return {"success": True, "changes": changes, "explanation": explanation}


def apply_implementation(change: dict) -> dict:
    """Apply a single change dict. Used by the healer and __main__ block."""
    repo_path = os.getenv("REPO_LOCAL_PATH", ".")

    if os.path.isabs(change["filepath"]):
        filepath = change["filepath"]
    else:
        filepath = os.path.join(repo_path, change["filepath"].lstrip("/").lstrip("\\"))

    if change["change_type"] == "create":
        return write_file(filepath, change["new_code"])

    if change["change_type"] == "edit":
        if not change.get("old_code"):
            return smart_apply(filepath, change)

        result = edit_file(filepath, change["old_code"], change["new_code"])
        if result["success"]:
            return result

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            old_normalised = "\n".join(line.rstrip() for line in change["old_code"].split("\n"))
            content_normalised = "\n".join(line.rstrip() for line in content.split("\n"))

            if old_normalised in content_normalised:
                updated = content_normalised.replace(old_normalised, change["new_code"], 1)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(updated)
                return {"success": True, "filepath": filepath, "message": "File edited (normalised match)"}

            return smart_apply(filepath, change)

        except Exception as e:
            return {"success": False, "filepath": filepath, "error": str(e)}

    return {"success": False, "error": f"Unknown change type: {change['change_type']}"}


def apply_changes(changes: list) -> list:
    """Apply every change in order and return one result dict per change."""
    return [apply_implementation(change) for change in changes]


def smart_apply(filepath: str, change: dict) -> dict:
    """Ask Claude to rewrite the file with the described change applied."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        prompt = f"""You are a precise code editor.

Here is the current file content:
{content}

Apply this change:
{change['explanation']}

New code to insert or use:
{change['new_code']}

Return the COMPLETE updated file content with the change applied.
No explanation, no markdown fences — just the raw file content."""

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8096,
            messages=[{"role": "user", "content": prompt}]
        )

        new_content = response.content[0].text.strip()

        if new_content.startswith("```"):
            lines = new_content.split("\n")
            new_content = "\n".join(lines[1:-1])

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

        return {"success": True, "filepath": filepath, "message": "File edited (smart apply)"}

    except Exception as e:
        return {"success": False, "filepath": filepath, "error": str(e)}


if __name__ == "__main__":
    import argparse
    from agent.tools.task_reader import get_task, parse_task
    from agent.tools.code_scanner import read_file
    from rich import print

    parser = argparse.ArgumentParser(description="Implement a GitHub issue against a specific file")
    parser.add_argument("--issue", type=int, required=True, help="GitHub issue number")
    parser.add_argument("--file", required=True, help="File path to implement against")
    args = parser.parse_args()

    raw = get_task(args.issue)
    task = parse_task(raw)
    print(f"Task: {task['title']}")

    file_data = read_file(args.file)
    if not file_data["success"]:
        print(f"[red]File not found: {args.file}[/red]")
        raise SystemExit(1)

    impl = implement_task(task, {args.file: file_data["content"]})
    print(f"\n[bold]Changes planned: {len(impl['changes'])}[/bold]")

    for i, change in enumerate(impl["changes"], 1):
        print(f"\n  [{i}] {change['change_type'].upper()} {change['filepath']}")
        print(f"       {change['explanation']}")
        result = apply_implementation(change)
        status = "✅" if result["success"] else "❌"
        msg = result.get("message") or result.get("error")
        print(f"       {status} {msg}")
