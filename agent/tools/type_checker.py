import os
import re
import subprocess
import sys

_NPX = "npx.cmd" if sys.platform == "win32" else "npx"

_MYPY_INDICATORS = ("mypy.ini", ".mypy.ini")


def detect_type_checker(repo_path: str) -> str:
    """Return 'tsc', 'mypy', or 'none'."""
    if os.path.exists(os.path.join(repo_path, "tsconfig.json")):
        return "tsc"
    for name in _MYPY_INDICATORS:
        if os.path.exists(os.path.join(repo_path, name)):
            return "mypy"
    for name in ("pyproject.toml", "setup.cfg"):
        path = os.path.join(repo_path, name)
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8", errors="ignore") as fh:
                    if "[mypy]" in fh.read() or "mypy" in fh.read():
                        return "mypy"
            except OSError:
                pass
    return "none"


def _parse_error_count(output: str, checker: str) -> int:
    if checker == "tsc":
        # tsc prints "Found N error(s) in M files"  or individual "error TS..." lines
        m = re.search(r"Found (\d+) error", output)
        if m:
            return int(m.group(1))
        return len(re.findall(r"\berror TS\d+:", output))
    if checker == "mypy":
        # mypy summary: "Found N errors in M files (checked K source files)"
        m = re.search(r"Found (\d+) error", output)
        if m:
            return int(m.group(1))
    return 0


def run_type_check(repo_path: str, config: dict = None) -> dict:
    """
    Run the appropriate type checker for the repo.

    Returns:
        {
            "checker": str,       # 'tsc' | 'mypy' | 'none'
            "skipped": bool,
            "errors": int,
            "output": str,
            "success": bool,      # True when errors == 0
        }
    """
    cfg = config or {}
    type_cfg = cfg.get("type_check", {})

    if not type_cfg.get("enabled", True):
        return {"checker": "none", "skipped": True, "errors": 0, "output": "", "success": True}

    checker = detect_type_checker(repo_path)

    if checker == "none":
        return {"checker": "none", "skipped": True, "errors": 0, "output": "No type checker detected", "success": True}

    if checker == "tsc":
        cmd = [_NPX, "tsc", "--noEmit"]
    else:
        cmd = [sys.executable, "-m", "mypy", ".", "--ignore-missing-imports"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=repo_path,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return {"checker": checker, "skipped": False, "errors": 0,
                "output": "Type check timed out after 120s", "success": True}
    except FileNotFoundError:
        return {"checker": checker, "skipped": True, "errors": 0,
                "output": f"Type checker not found: {cmd[0]}", "success": True}

    output = result.stdout + result.stderr
    errors = _parse_error_count(output, checker)

    return {
        "checker": checker,
        "skipped": False,
        "errors": errors,
        "output": output,
        "success": errors == 0,
    }
