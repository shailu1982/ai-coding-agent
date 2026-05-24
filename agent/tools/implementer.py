import os
import anthropic
from dotenv import load_dotenv

load_dotenv("config/.env")

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def write_file(filepath: str, content: str) -> dict:
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return {
            "success": True,
            "filepath": filepath,
            "message": f"File written successfully"
        }
    except Exception as e:
        return {
            "success": False,
            "filepath": filepath,
            "error": str(e)
        }


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

        return {
            "success": True,
            "filepath": filepath,
            "message": "File edited successfully"
        }

    except FileNotFoundError:
        return {
            "success": False,
            "filepath": filepath,
            "error": "File not found"
        }
    except Exception as e:
        return {
            "success": False,
            "filepath": filepath,
            "error": str(e)
        }


def delete_file(filepath: str) -> dict:
    try:
        os.remove(filepath)
        return {
            "success": True,
            "filepath": filepath,
            "message": "File deleted successfully"
        }
    except Exception as e:
        return {
            "success": False,
            "filepath": filepath,
            "error": str(e)
        }


def run_linter(filepath: str) -> dict:
    import subprocess
    ext = os.path.splitext(filepath)[1]

    if ext in [".ts", ".tsx", ".js", ".jsx"]:
        cmd = ["npx", "eslint", filepath, "--format", "compact"]
    elif ext == ".py":
        cmd = ["flake8", filepath]
    else:
        return {
            "success": True,
            "filepath": filepath,
            "message": "No linter available for this file type"
        }

    result = subprocess.run(cmd, capture_output=True, text=True)
    return {
        "success": result.returncode == 0,
        "filepath": filepath,
        "output": result.stdout + result.stderr
    }


def implement_task(task: dict, file_contents: dict) -> dict:
    # Build the prompt
    files_context = ""
    for filepath, content in file_contents.items():
        files_context += f"\n\n--- FILE: {filepath} ---\n{content}"

    criteria = "\n".join(
        f"- {c}" for c in task.get("acceptance_criteria", [])
    )

    prompt = f"""You are an expert software engineer. 
Your job is to implement the following task exactly as described.

## Task
Title: {task['title']}

## Description
{task['description']}

## Acceptance Criteria
{criteria}

## Current Code
{files_context}

## Instructions
1. Analyse the current code carefully
2. Make the minimal change needed to satisfy all acceptance criteria
3. Do not change anything unrelated to the task
4. Return your response in this exact format:

FILEPATH: <the file path you are editing>
CHANGE_TYPE: <edit or create>
OLD_CODE: <the exact existing code block you are replacing — leave empty if creating>
NEW_CODE: <the new code to replace it with>
EXPLANATION: <one sentence explaining what you changed and why>

Only return one change at a time. Be precise."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text

    # Parse the response
    result = {
        "success": True,
        "raw_response": raw,
        "filepath": None,
        "change_type": None,
        "old_code": None,
        "new_code": None,
        "explanation": None
    }

    for line in raw.split("\n"):
        if line.startswith("FILEPATH:"):
            result["filepath"] = line.replace("FILEPATH:", "").strip()
        elif line.startswith("CHANGE_TYPE:"):
            result["change_type"] = line.replace("CHANGE_TYPE:", "").strip()
        elif line.startswith("EXPLANATION:"):
            result["explanation"] = line.replace("EXPLANATION:", "").strip()

    # Extract OLD_CODE and NEW_CODE blocks
    if "OLD_CODE:" in raw and "NEW_CODE:" in raw:
        old_start = raw.find("OLD_CODE:") + len("OLD_CODE:")
        new_start = raw.find("NEW_CODE:")
        expl_start = raw.find("EXPLANATION:")

        result["old_code"] = raw[old_start:new_start].strip()
        result["new_code"] = raw[new_start + len("NEW_CODE:"):expl_start].strip()

    return result


def apply_implementation(impl: dict) -> dict:
    repo_path = os.getenv("REPO_LOCAL_PATH", ".")

    # Use the full path if already absolute, otherwise join with repo path
    if os.path.isabs(impl["filepath"]):
        filepath = impl["filepath"]
    else:
        filepath = os.path.join(repo_path, impl["filepath"].lstrip("/"))

    if impl["change_type"] == "create":
        return write_file(filepath, impl["new_code"])

    elif impl["change_type"] == "edit":
        # First try exact match
        result = edit_file(filepath, impl["old_code"], impl["new_code"])
        if result["success"]:
            return result

        # If exact match fails, try stripping and normalising whitespace
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            old_normalised = "\n".join(
                line.rstrip() for line in impl["old_code"].split("\n")
            )
            content_normalised = "\n".join(
                line.rstrip() for line in content.split("\n")
            )

            if old_normalised in content_normalised:
                updated = content_normalised.replace(
                    old_normalised,
                    impl["new_code"],
                    1
                )
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(updated)
                return {
                    "success": True,
                    "filepath": filepath,
                    "message": "File edited successfully (normalised match)"
                }

            # Last resort — ask Claude for the raw new file content
            return smart_apply(filepath, impl)

        except Exception as e:
            return {
                "success": False,
                "filepath": filepath,
                "error": str(e)
            }

    return {
        "success": False,
        "error": "Unknown change type"
    }


def smart_apply(filepath: str, impl: dict) -> dict:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        prompt = f"""You are a precise code editor.

Here is the current file content:
{content}

Here is the change that needs to be applied:
{impl['explanation']}

New code to insert:
{impl['new_code']}

Return the COMPLETE updated file content with the change applied.
Do not add any explanation, just return the raw file content."""

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8096,
            messages=[{"role": "user", "content": prompt}]
        )

        new_content = response.content[0].text.strip()

        # Strip markdown code fences if present
        if new_content.startswith("```"):
            lines = new_content.split("\n")
            new_content = "\n".join(lines[1:-1])

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(new_content)

        return {
            "success": True,
            "filepath": filepath,
            "message": "File edited successfully (smart apply)"
        }

    except Exception as e:
        return {
            "success": False,
            "filepath": filepath,
            "error": str(e)
        }

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
        if "SearchBar.tsx" in r["filepath"]:
            target_file = r["filepath"]
            break

    if not target_file:
        print("[red]SearchBar.tsx not found![/red]")
        exit()

    print(f"Found: {target_file}")

    print("\n[bold]Step 3: Reading file...[/bold]")
    file_data = read_file(target_file)
    print(f"Lines: {file_data['line_count']}")

    print("\n[bold]Step 4: Asking Claude to implement the task...[/bold]")
    impl = implement_task(
        task,
        {target_file: file_data["content"]}
    )

    print("\n[bold]Claude's plan:[/bold]")
    print(f"File     : {impl['filepath']}")
    print(f"Type     : {impl['change_type']}")
    print(f"Explain  : {impl['explanation']}")

    print("\n[bold]Step 5: Applying the change...[/bold]")
    apply_result = apply_implementation(impl)
    print(apply_result)