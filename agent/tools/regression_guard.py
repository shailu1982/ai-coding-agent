import os
import re
import subprocess
import sys
from dotenv import load_dotenv

load_dotenv("config/.env")

_NPX = "npx.cmd" if sys.platform == "win32" else "npx"

_PYTEST_INDICATORS = (
    "pytest.ini", "conftest.py", "pyproject.toml", "setup.cfg", "setup.py"
)


def _detect_runner(repo_path: str, config: dict = None) -> str:
    """
    Return 'custom', 'jest', 'pytest', or 'none'.
    'custom' means a test_command is configured and takes precedence.
    """
    test_cmd = (config or {}).get("test_command") or os.getenv("TEST_COMMAND")
    if test_cmd:
        return "custom"
    if os.path.exists(os.path.join(repo_path, "package.json")):
        return "jest"
    if any(os.path.exists(os.path.join(repo_path, f)) for f in _PYTEST_INDICATORS):
        return "pytest"
    return "none"


def _parse_counts(output: str, runner: str) -> tuple:
    """Return (passed, failed) parsed from structured test output."""
    if runner in ("jest", "custom"):
        # Jest prints: "Tests:       3 failed, 15 passed, 18 total"
        m = re.search(r'Tests:\s+(?:(\d+) failed,\s+)?(\d+) passed', output)
        if m:
            return int(m.group(2)), int(m.group(1) or 0)

    # pytest / fallback: "5 passed" and "2 failed" appear on the summary line
    passed = 0
    failed = 0
    m = re.search(r'(\d+) passed', output)
    if m:
        passed = int(m.group(1))
    m = re.search(r'(\d+) failed', output)
    if m:
        failed = int(m.group(1))
    return passed, failed


def _run_suite(repo_path: str, config: dict = None) -> dict:
    cfg = config or {}
    runner = _detect_runner(repo_path, cfg)
    timeout = cfg.get("test_suite_timeout") or int(os.getenv("TEST_SUITE_TIMEOUT", "300"))

    if runner == "none":
        return {
            "skipped": True, "runner": "none",
            "passed": 0, "failed": 0, "output": "No test runner detected in repo"
        }

    if runner == "custom":
        test_cmd = cfg.get("test_command") or os.getenv("TEST_COMMAND")
        cmd = test_cmd.split()
    elif runner == "jest":
        cmd = [_NPX, "jest", "--no-coverage", "--watchAll=false", "--passWithNoTests"]
    else:
        cmd = [sys.executable, "-m", "pytest", "--tb=no", "-q"]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=repo_path, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return {
            "skipped": False, "runner": runner,
            "passed": 0, "failed": 0,
            "output": f"Test suite timed out after {timeout}s",
            "timed_out": True
        }
    except FileNotFoundError:
        return {
            "skipped": True, "runner": runner,
            "passed": 0, "failed": 0,
            "output": f"Test runner not found: {cmd[0]}"
        }

    output = result.stdout + result.stderr
    passed, failed = _parse_counts(output, runner)

    return {
        "skipped": False, "runner": runner,
        "passed": passed, "failed": failed,
        "returncode": result.returncode, "output": output
    }


def capture_baseline(repo_path: str, config: dict = None) -> dict:
    """
    Run the full test suite before any changes and record the result.
    Call this after codebase scan, before implementation.
    """
    return _run_suite(repo_path, config)


def check_regressions(repo_path: str, baseline: dict, config: dict = None) -> dict:
    """
    Run the full test suite after changes and compare to the baseline.

    Returns:
        {
            "regressions": int,   # new failures introduced (0 = clean)
            "skipped": bool,
            "baseline_failed": int,
            "after_failed": int,
            "snippet": str        # tail of output for the error message
        }
    """
    if baseline.get("skipped"):
        return {"regressions": 0, "skipped": True, "snippet": ""}

    after = _run_suite(repo_path, config)

    if after.get("skipped") or after.get("timed_out"):
        return {"regressions": 0, "skipped": True, "snippet": after.get("output", "")}

    new_failures = max(0, after["failed"] - baseline["failed"])

    return {
        "regressions": new_failures,
        "skipped": False,
        "baseline_failed": baseline["failed"],
        "after_failed": after["failed"],
        "baseline_passed": baseline["passed"],
        "after_passed": after["passed"],
        "snippet": after["output"][-2000:].strip() if new_failures else "",
    }
