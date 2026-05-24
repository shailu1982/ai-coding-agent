import os
from dotenv import load_dotenv
from agent.utils.retry import RetryingClient

load_dotenv("config/.env")

client = RetryingClient(api_key=os.getenv("ANTHROPIC_API_KEY"))

_RUNNER_ERRORS = [
    "command not found",
    "not found",
    "enoent",
    "cannot find module 'jest'",
    "no module named pytest",
    "jest: command",
    "error: cannot find",
]


def is_runner_error(output: str) -> bool:
    """True when the test runner itself failed to start rather than tests failing."""
    lower = output.lower()
    has_runner_error = any(e in lower for e in _RUNNER_ERRORS)
    has_test_results = any(t in lower for t in ["fail", "pass", "error", "assert", "expect"])
    return has_runner_error and not has_test_results


def fix_failing_tests(
    impl_filepath: str,
    test_filepath: str,
    failure_output: str,
    attempt: int,
) -> dict:
    """
    Read the implementation and test files, ask Claude to diagnose the failures,
    and write the fix back to disk.

    The healer biases toward fixing the implementation. It will only fix the
    test file if the failure is clearly a setup/import problem, not a spec problem.
    """
    try:
        with open(impl_filepath, "r", encoding="utf-8") as f:
            impl_content = f.read()
    except Exception as e:
        return {"success": False, "error": f"Could not read implementation: {e}"}

    try:
        with open(test_filepath, "r", encoding="utf-8") as f:
            test_content = f.read()
    except Exception as e:
        return {"success": False, "error": f"Could not read test file: {e}"}

    prompt = f"""You are an expert debugger. Tests are failing after an AI-generated implementation.
Your job is to fix the code so the tests pass.

## Attempt
{attempt}

## Test Failure Output
```
{failure_output[:3000]}
```

## Test File — {os.path.basename(test_filepath)}
(These tests define the specification. Only change them if there is a clear setup or import error, not to weaken the assertions.)
```
{test_content}
```

## Implementation File — {os.path.basename(impl_filepath)}
```
{impl_content}
```

## Instructions
1. Carefully read the failure output and identify the root cause
2. Decide whether to fix the implementation or (only if unavoidable) the test file
3. Return ONLY in this exact format — no other text:

FIX_TARGET: implementation
EXPLANATION: <one sentence describing the root cause and what you changed>
FIXED_CODE:
<complete corrected file content, no markdown fences>"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8096,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()

    fix_target = "implementation"
    explanation = ""
    fixed_code = ""

    for line in raw.split("\n"):
        if line.startswith("FIX_TARGET:"):
            fix_target = line.replace("FIX_TARGET:", "").strip().lower()
        elif line.startswith("EXPLANATION:"):
            explanation = line.replace("EXPLANATION:", "").strip()

    if "FIXED_CODE:" in raw:
        code_start = raw.find("FIXED_CODE:") + len("FIXED_CODE:")
        fixed_code = raw[code_start:].strip()
        if fixed_code.startswith("```"):
            lines = fixed_code.split("\n")
            fixed_code = "\n".join(lines[1:-1])

    if not fixed_code:
        return {"success": False, "error": "Healer returned no fixed code"}

    target_path = impl_filepath if fix_target == "implementation" else test_filepath

    try:
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(fixed_code)
    except Exception as e:
        return {"success": False, "error": f"Could not write fix: {e}"}

    return {
        "success": True,
        "fix_target": fix_target,
        "filepath": target_path,
        "explanation": explanation,
    }
