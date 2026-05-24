import copy
import os

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

DEFAULTS: dict = {
    "max_relevant_files": 5,
    "max_heal_attempts": 3,
    "regression_guard": True,
    "test_command": None,
    "test_suite_timeout": 300,
    "base_branch": "main",
    "review": {
        "security": True,
        "optimize": True,
        "seo": True,
        "readme": True,
    },
    "labels": {
        "trigger": "ai-implement",
        "processing": "ai-processing",
        "done": "ai-done",
        "failed": "ai-failed",
    },
    "notifications": {
        "slack_webhook": None,
        "on_success": False,
        "on_failure": True,
    },
    "type_check": {
        "enabled": True,
        "blocking": False,
    },
    "reviewers": {
        "users": [],
        "teams": [],
    },
}

_ENV_OVERRIDES = {
    "BASE_BRANCH":          ("base_branch",          str),
    "MAX_HEAL_ATTEMPTS":    ("max_heal_attempts",     int),
    "REGRESSION_GUARD":     ("regression_guard",      lambda v: v.lower() not in ("false", "0", "off")),
    "TEST_COMMAND":         ("test_command",          lambda v: v or None),
    "TEST_SUITE_TIMEOUT":   ("test_suite_timeout",    int),
    "MAX_RELEVANT_FILES":   ("max_relevant_files",    int),
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_repo_config(repo_path: str) -> dict:
    """
    Load config for a target repo by merging (lowest → highest priority):
      1. Hardcoded DEFAULTS
      2. .agent.yml in the repo root (if present)
      3. Environment variable overrides
    """
    config = copy.deepcopy(DEFAULTS)

    agent_yml = os.path.join(repo_path, ".agent.yml")
    if os.path.isfile(agent_yml):
        if not _YAML_AVAILABLE:
            import warnings
            warnings.warn(".agent.yml found but pyyaml is not installed — ignoring repo config")
        else:
            with open(agent_yml, encoding="utf-8") as f:
                repo_cfg = yaml.safe_load(f) or {}
            if isinstance(repo_cfg, dict):
                config = _deep_merge(config, repo_cfg)

    for env_var, (key, cast) in _ENV_OVERRIDES.items():
        raw = os.getenv(env_var)
        if raw is not None and raw != "":
            try:
                config[key] = cast(raw)
            except (ValueError, TypeError):
                pass

    # Nested env overrides
    slack = os.getenv("SLACK_WEBHOOK_URL")
    if slack:
        config["notifications"]["slack_webhook"] = slack

    return config
