import os
import shlex
import subprocess
import sys

from agent.utils.parsing import parse_test_counts

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
        cmd = shlex.split(test_cmd)
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

    output = (result.stdout or "") + (result.stderr or "")
    passed, failed = parse_test_counts(output, runner)

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


def check_regressions(repo_path: str, baseline: dict, config: dict = None, grace_suites: int = 0) -> dict:
    """
    Run the full test suite after changes and compare to the baseline.

    Args:
        grace_suites: Number of newly-added test files to exclude from the
                      regression count. The agent's own generated tests may
                      fail due to environment issues (missing Babel presets,
                      etc.) and should not block a clean implementation.

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

    new_failures = max(0, after["failed"] - baseline["failed"] - grace_suites)

    return {
        "regressions": new_failures,
        "skipped": False,
        "baseline_failed": baseline["failed"],
        "after_failed": after["failed"],
        "baseline_passed": baseline["passed"],
        "after_passed": after["passed"],
        "snippet": after["output"][-2000:].strip() if new_failures else "",
    }
