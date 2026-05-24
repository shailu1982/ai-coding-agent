import os
import fnmatch
from pathlib import Path
from dotenv import load_dotenv

load_dotenv("config/.env")

# File types we care about
INCLUDE_EXTENSIONS = [
    ".ts", ".tsx", ".js", ".jsx",
    ".py", ".json", ".md", ".css",
    ".html", ".env.example"
]

# Folders we want to skip
IGNORE_DIRS = [
    "node_modules", ".git", "venv",
    "__pycache__", "dist", "build",
    ".next", "coverage"
]


def get_repo_path() -> str:
    path = os.getenv("REPO_LOCAL_PATH", ".")
    return path


def get_file_tree(root: str = None) -> str:
    if root is None:
        root = get_repo_path()

    tree_lines = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Remove ignored directories in place
        dirnames[:] = [
            d for d in dirnames
            if d not in IGNORE_DIRS
        ]

        level = dirpath.replace(root, "").count(os.sep)
        indent = "  " * level
        folder = os.path.basename(dirpath)

        if level == 0:
            tree_lines.append(f"{folder}/")
        else:
            tree_lines.append(f"{indent}{folder}/")

        sub_indent = "  " * (level + 1)
        for filename in sorted(filenames):
            ext = Path(filename).suffix
            if ext in INCLUDE_EXTENSIONS:
                tree_lines.append(f"{sub_indent}{filename}")

    return "\n".join(tree_lines)


def list_files(root: str = None, extensions: list = None) -> list:
    if root is None:
        root = get_repo_path()
    if extensions is None:
        extensions = INCLUDE_EXTENSIONS

    matched_files = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in IGNORE_DIRS
        ]

        for filename in filenames:
            ext = Path(filename).suffix
            if ext in extensions:
                full_path = os.path.join(dirpath, filename)
                matched_files.append(full_path)

    return matched_files


def read_file(filepath: str) -> dict:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.split("\n")
        return {
            "success": True,
            "filepath": filepath,
            "content": content,
            "line_count": len(lines)
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


def search_code(query: str, root: str = None) -> list:
    if root is None:
        root = get_repo_path()

    results = []
    files = list_files(root)

    for filepath in files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()

            matches = []
            for i, line in enumerate(lines, 1):
                if query.lower() in line.lower():
                    matches.append({
                        "line_number": i,
                        "content": line.rstrip()
                    })

            if matches:
                results.append({
                    "filepath": filepath,
                    "matches": matches
                })

        except Exception:
            continue

    return results


# Quick test
if __name__ == "__main__":
    from rich import print

    repo_path = os.getenv("REPO_LOCAL_PATH", ".")

    print("\n[bold]Step 1: File tree[/bold]")
    tree = get_file_tree(repo_path)
    # Print first 30 lines only
    lines = tree.split("\n")[:30]
    print("\n".join(lines))
    print(f"... ({len(tree.split(chr(10)))} total lines)")

    print("\n[bold]Step 2: List .tsx files[/bold]")
    tsx_files = list_files(repo_path, [".tsx"])
    for f in tsx_files[:5]:
        print(f" • {f}")
    print(f"... ({len(tsx_files)} total .tsx files)")

    print("\n[bold]Step 3: Search for SearchBar[/bold]")
    results = search_code("SearchBar", repo_path)
    for r in results[:3]:
        print(f"\n📄 {r['filepath']}")
        for m in r['matches'][:2]:
            print(f"   Line {m['line_number']}: {m['content']}")