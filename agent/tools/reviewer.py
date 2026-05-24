import os
import subprocess
from dotenv import load_dotenv
from agent.utils.retry import RetryingClient

load_dotenv("config/.env")

client = RetryingClient(api_key=os.getenv("ANTHROPIC_API_KEY"))


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

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": f"""Review this code for security vulnerabilities only.
Look for: XSS, injection attacks, exposed secrets or tokens, insecure data handling,
missing input validation, unsafe use of eval or exec, and insecure dependencies.

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

        return {
            "success": True,
            "filepath": filepath,
            "tool": "claude",
            "output": response.content[0].text
        }

    except Exception as e:
        return {"success": False, "filepath": filepath, "error": str(e)}


def optimize_code(filepath: str) -> dict:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        ext = os.path.splitext(filepath)[1]

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": f"""Review this code for performance and quality improvements only.
Look for: redundant computations, inefficient loops, unnecessary object or array creation,
oversized imports that could be tree-shaken or lazy-loaded, dead code, missing error
handling at I/O boundaries, and readability issues that increase maintenance cost.
File extension: {ext}

File: {filepath}
Code:
{content}

Reply in this format:
OPTIMIZATIONS_FOUND: yes or no
OPTIMIZATIONS:
- optimization 1
- optimization 2
UPDATED_CODE: <full updated file with optimizations applied, or omit if no changes needed>"""
            }]
        )

        raw = response.content[0].text
        updated_code = None

        if "UPDATED_CODE:" in raw:
            updated_start = raw.find("UPDATED_CODE:") + len("UPDATED_CODE:")
            updated_code = raw[updated_start:].strip()
            if updated_code.startswith("```"):
                lines = updated_code.split("\n")
                updated_code = "\n".join(lines[1:-1])
            if not updated_code:
                updated_code = None

        return {
            "success": True,
            "filepath": filepath,
            "output": raw,
            "updated_code": updated_code
        }

    except Exception as e:
        return {"success": False, "filepath": filepath, "error": str(e)}


def check_seo(filepath: str) -> dict:
    ext = os.path.splitext(filepath)[1]

    if ext not in (".tsx", ".jsx", ".html"):
        return {
            "success": True,
            "filepath": filepath,
            "output": "SEO check skipped — not a UI file",
            "issues": []
        }

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": f"""Review this file for SEO and accessibility issues only.
Look for: missing alt tags, missing aria labels, missing semantic HTML,
missing meta tags, poor heading hierarchy, missing title attributes,
and keyboard navigation problems.

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
        issues = [
            line.strip()[2:] for line in raw.split("\n")
            if line.strip().startswith("- ")
        ]

        return {
            "success": True,
            "filepath": filepath,
            "output": raw,
            "issues": issues
        }

    except Exception as e:
        return {"success": False, "filepath": filepath, "error": str(e)}


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
If a changelog or recent changes section exists, update it.
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

        return {"success": True, "filepath": readme_path}

    except Exception as e:
        return {"success": False, "filepath": readme_path, "error": str(e)}


if __name__ == "__main__":
    import argparse
    from rich import print

    parser = argparse.ArgumentParser(description="Run review checks on a file")
    parser.add_argument("--file", required=True, help="File to review")
    args = parser.parse_args()

    print(f"\n[bold cyan]Security scan:[/bold cyan]")
    sec = security_scan(args.file)
    print(sec["output"][:400])

    print(f"\n[bold cyan]Optimization check:[/bold cyan]")
    opt = optimize_code(args.file)
    print(opt["output"][:400])

    print(f"\n[bold cyan]SEO / accessibility check:[/bold cyan]")
    seo = check_seo(args.file)
    print(f"Issues found: {len(seo.get('issues', []))}")
    for issue in seo.get("issues", []):
        print(f"  • {issue}")
