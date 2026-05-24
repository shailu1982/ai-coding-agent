import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv("config/.env")

INCLUDE_EXTENSIONS = [
    ".ts", ".tsx", ".js", ".jsx",
    ".py", ".json", ".md", ".css",
    ".html", ".env.example"
]

IGNORE_DIRS = [
    "node_modules", ".git", "venv",
    "__pycache__", "dist", "build",
    ".next", "coverage"
]


def get_repo_path() -> str:
    return os.getenv("REPO_LOCAL_PATH", ".")


def get_file_tree(root: str = None) -> str:
    if root is None:
        root = get_repo_path()

    tree_lines = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]

        level = dirpath.replace(root, "").count(os.sep)
        indent = "  " * level
        folder = os.path.basename(dirpath)

        tree_lines.append(f"{indent}{folder}/")

        sub_indent = "  " * (level + 1)
        for filename in sorted(filenames):
            if Path(filename).suffix in INCLUDE_EXTENSIONS:
                tree_lines.append(f"{sub_indent}{filename}")

    return "\n".join(tree_lines)


def list_files(root: str = None, extensions: list = None) -> list:
    if root is None:
        root = get_repo_path()
    if extensions is None:
        extensions = INCLUDE_EXTENSIONS

    matched_files = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]

        for filename in filenames:
            if Path(filename).suffix in extensions:
                matched_files.append(os.path.join(dirpath, filename))

    return matched_files


def read_file(filepath: str) -> dict:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        return {
            "success": True,
            "filepath": filepath,
            "content": content,
            "line_count": content.count("\n") + 1
        }

    except FileNotFoundError:
        return {"success": False, "filepath": filepath, "error": "File not found"}
    except Exception as e:
        return {"success": False, "filepath": filepath, "error": str(e)}


def search_code(query: str, root: str = None) -> list:
    if root is None:
        root = get_repo_path()

    results = []

    for filepath in list_files(root):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()

            matches = [
                {"line_number": i, "content": line.rstrip()}
                for i, line in enumerate(lines, 1)
                if query.lower() in line.lower()
            ]

            if matches:
                results.append({"filepath": filepath, "matches": matches})

        except Exception:
            continue

    return results


if __name__ == "__main__":
    import argparse
    from rich import print

    parser = argparse.ArgumentParser(description="Scan the target repository")
    parser.add_argument("--query", default=None, help="Optional search term")
    args = parser.parse_args()

    repo_path = get_repo_path()

    print(f"\n[bold cyan]File tree:[/bold cyan] {repo_path}")
    tree = get_file_tree(repo_path)
    lines = tree.split("\n")
    print("\n".join(lines[:40]))
    if len(lines) > 40:
        print(f"  ... ({len(lines)} total lines)")

    if args.query:
        print(f"\n[bold cyan]Search results for '{args.query}':[/bold cyan]")
        results = search_code(args.query, repo_path)
        for r in results[:5]:
            print(f"\n  {r['filepath']}")
            for m in r["matches"][:3]:
                print(f"    Line {m['line_number']}: {m['content']}")
        if not results:
            print("  No matches found.")
