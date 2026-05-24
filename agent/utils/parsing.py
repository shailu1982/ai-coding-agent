"""
Shared parsing utilities for handling Claude API responses and test output.
"""

import re


def strip_code_fences(text: str) -> str:
    """Remove markdown code fences from Claude's response.

    Handles responses wrapped in ```lang ... ``` blocks.  If the text does
    not start with a code fence, it is returned unchanged.
    """
    text = text.strip()
    if not text.startswith("```"):
        return text

    lines = text.split("\n")

    # Remove the opening fence (e.g., ```python)
    lines = lines[1:]

    # Remove the closing fence if present
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]

    return "\n".join(lines)


def parse_test_counts(output: str, runner: str = "auto") -> tuple[int, int]:
    """Parse (passed, failed) counts from test runner output.

    Uses structured regex patterns rather than naive substring counting
    to avoid false positives from test names or assertion messages.

    Args:
        output: Combined stdout + stderr from the test runner.
        runner: One of 'jest', 'pytest', 'custom', or 'auto' (try all).

    Returns:
        Tuple of (passed_count, failed_count).
    """
    if runner in ("jest", "custom", "auto"):
        # Jest prints: "Tests:       3 failed, 15 passed, 18 total"
        m = re.search(r'Tests:\s+(?:(\d+) failed,\s+)?(\d+) passed', output)
        if m:
            return int(m.group(2)), int(m.group(1) or 0)

    # pytest / fallback: "5 passed" and "2 failed" on the summary line
    passed = 0
    failed = 0
    m = re.search(r'(\d+) passed', output)
    if m:
        passed = int(m.group(1))
    m = re.search(r'(\d+) failed', output)
    if m:
        failed = int(m.group(1))
    return passed, failed
