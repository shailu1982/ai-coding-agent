import os
import subprocess
import anthropic
from dotenv import load_dotenv

load_dotenv("config/.env")

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def security_scan(filepath: str) -> dict:
    ext = os.path.splitext(filepath)[1]

    if ext == ".py":
        result = subprocess.run(
            ["bandit", "-r", filepath],
            capture_output=True,
            text=True
        )
        return {
            "success": result.returncode == 0,
            "filepath": filepath,
            "tool": "bandit",
            "output": result.stdout + result.stderr
        }

    # For JS/TS files use Claude to scan
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": f"""Review this code for security vulnerabilities only.
Look for: XSS, injection, exposed secrets, insecure dependencies,
unsafe data handling, missing input validation.

File: {filepath}
Code:
{content}

Reply in this format:
ISSUES_FOUND: yes or no
SEVERITY: low / medium / high / none
ISSUES:
- issue 1
- issue 2
RECOMMENDATION: one line fix suggestion"""
            }]
        )

        raw = response.content[0].text
        return {
            "success": True,
            "filepath": filepath,
            "tool": "claude",
            "output": raw
        }

    except Exception as e:
        return {
            "success": False,
            "filepath": filepath,
            "error": str(e)
        }


def optimize_code(filepath: str) -> dict:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": f"""Review this code for performance and quality improvements only.
Look for: unnecessary re-renders, missing memoization, redundant code,
inefficient loops, large bundle imports, accessibility issues.

File: {filepath}
Code:
{content}

Reply in this format:
OPTIMIZATIONS_FOUND: yes or no
OPTIMIZATIONS:
- optimization 1
- optimization 2
UPDATED_CODE: <full updated file with optimizations applied>"""
            }]
        )

        raw = response.content[0].text

        # Extract updated code if provided
        updated_code = None
        if "UPDATED_CODE:" in raw:
            updated_start = raw.find("UPDATED_CODE:") + len("UPDATED_CODE:")
            updated_code = raw[updated_start:].strip()
            if updated_code.startswith("```"):
                lines = updated_code.split("\n")
                updated_code = "\n".join(lines[1:-1])

        return {
            "success": True,
            "filepath": filepath,
            "output": raw,
            "updated_code": updated_code
        }

    except Exception as e:
        return {
            "success": False,
            "filepath": filepath,
            "error": str(e)
        }


def check_seo(filepath: str) -> dict:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        ext = os.path.splitext(filepath)[1]
        if ext not in [".tsx", ".jsx", ".html"]:
            return {
                "success": True,
                "filepath": filepath,
                "output": "SEO check skipped — not a UI file",
                "issues": []
            }

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": f"""Review this React/HTML file for SEO and accessibility issues only.
Look for: missing alt tags, missing aria labels, missing semantic HTML,
missing meta tags, poor heading hierarchy, missing title attributes.

File: {filepath}
Code:
{content}

Reply in this format:
ISSUES_FOUND: yes or no
ISSUES:
- issue 1
- issue 2
RECOMMENDATION: one line fix suggestion"""
            }]
        )

        raw = response.content[0].text
        issues = []
        for line in raw.split("\n"):
            if line.strip().startswith("- "):
                issues.append(line.strip()[2:])

        return {
            "success": True,
            "filepath": filepath,
            "output": raw,
            "issues": issues
        }

    except Exception as e:
        return {
            "success": False,
            "filepath": filepath,
            "error": str(e)
        }


def update_readme(repo_path: str, changes_summary: str) -> dict:
    readme_path = os.path.join(repo_path, "README.md")

    try:
        if os.path.exists(readme_path):
            with open(readme_path, "r", encoding="utf-8") as f:
                existing = f.read()
        else:
            existing = "# Project\n"

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": f"""Update this README.md to reflect the following changes.
Only update relevant sections. Do not rewrite the whole README.
If a changelog or recent changes section exists update it.
If not, add a small ## Recent Changes section at the bottom.

Current README:
{existing}

Changes made:
{changes_summary}

Return the complete updated README content only.
No explanation, no markdown fences."""
            }]
        )

        updated = response.content[0].text.strip()

        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(updated)

        return {
            "success": True,
            "filepath": readme_path,
            "message": "README updated successfully"
        }

    except Exception as e:
        return {
            "success": False,
            "filepath": readme_path,
            "error": str(e)
        }


# Quick test
if __name__ == "__main__":
    from rich import print

    repo_path = os.getenv("REPO_LOCAL_PATH", ".")
    target_file = os.path.join(
        repo_path, "src", "components", "SearchBar.tsx"
    )

    print("\n[bold]Step 1: Security scan...[/bold]")
    sec = security_scan(target_file)
    print(sec["output"][:300])

    print("\n[bold]Step 2: Code optimisation...[/bold]")
    opt = optimize_code(target_file)
    print(opt["output"][:300])

    print("\n[bold]Step 3: SEO check...[/bold]")
    seo = check_seo(target_file)
    print(f"Issues found: {len(seo['issues'])}")
    for issue in seo["issues"]:
        print(f"  • {issue}")

    print("\n[bold]Step 4: Updating README...[/bold]")
    result = update_readme(
        repo_path,
        "Added result count label to SearchBar component showing number of search results"
    )
    print(result)