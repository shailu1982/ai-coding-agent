# AI Coding Agent

An autonomous AI agent that watches your GitHub issues and implements them end-to-end — no human intervention required. Label an issue `ai-implement`, walk away, and the agent creates a branch, writes code, generates tests, self-heals failures, runs a full review, and opens a pull request.

## How It Works

```
You label an issue "ai-implement"
        ↓
GitHub Actions runs every 10 minutes
        ↓
Discover job finds pending issues, claims them with "ai-processing"
        ↓
Worker jobs run in parallel (one per issue)
        ↓
8-stage pipeline runs autonomously
        ↓
Issue labeled "ai-done" + comment with PR link
```

### The 8-Stage Pipeline

| Stage | What it does |
|-------|-------------|
| 1. Task Reading | Fetches the issue and extracts title, description, and acceptance criteria |
| 2. Branch Creation | Validates the base branch and creates a feature branch (`issue-<number>`) |
| 3. Code Analysis | Scans the codebase, identifies relevant files, and captures a test baseline |
| 4. Implementation | Uses Claude to design and apply multi-file code changes with linting |
| 4b. Type Checking | Runs `tsc` or `mypy` (auto-detected) to catch type errors early |
| 5. Test Writing | Generates framework-appropriate tests (Jest/React Testing Library/pytest) with a self-healing loop |
| 6. Regression Guard | Re-runs the full test suite and compares against the pre-change baseline |
| 7. Review | Security scan (Bandit for Python, Claude for JS/TS), optimization pass, and SEO/accessibility check |
| 8. PR Creation | Commits, pushes, and opens a pull request with an auto-generated description |

### Self-Healing Loop (Stage 5)

When generated tests fail, the agent enters a heal loop:

1. Claude reads the failing output, implementation, and test files
2. It diagnoses the root cause and fixes the **implementation** (not the tests, unless the failure is clearly a setup/import issue)
3. Tests are re-run — if they pass, the loop exits; otherwise, it retries up to `MAX_HEAL_ATTEMPTS` times (default: 3)

### Regression Guard (Stage 6)

Before any changes are made (end of Stage 3), the agent runs the full test suite and records a baseline. After implementation, it runs the suite again and compares:

- **0 new failures**: clean — the agent continues
- **New failures detected**: the pipeline aborts with a detailed error, preventing regressions from being merged

### Few-Shot Learning

The agent stores successful implementations in an example store (`examples/store.json`). On future tasks, it retrieves similar past examples by keyword similarity and includes them as few-shot context for Claude, improving code quality over time.

### Issue Label State Machine

| Label | Meaning |
|-------|---------| 
| `ai-implement` | Queued — agent will pick this up on the next run |
| `ai-processing` | In progress — pipeline is currently running |
| `ai-done` | Complete — PR link is in the issue comments |
| `ai-failed` | Failed — error details in the issue comments; remove this label and re-add `ai-implement` to retry |

## Setup

### 1. Fork or clone this repo

```bash
git clone <this-repo-url>
cd ai-coding-agent
```

### 2. Create a GitHub Personal Access Token

Go to `GitHub → Settings → Developer settings → Personal access tokens` and create a token with `repo` scope. This token is used to read issues, push branches, and create PRs on your target repo.

### 3. Add secrets to this repo

Go to `Settings → Secrets and variables → Actions` in this repo and add:

| Type | Name | Value |
|------|------|-------|
| Secret | `GH_PAT` | Your personal access token (needs `repo` scope) |
| Secret | `ANTHROPIC_API_KEY` | Your Anthropic API key (`sk-ant-...`) |
| Secret | `TARGET_REPO` | The repo the agent should work on (`owner/repo-name`) |
| Secret | `SLACK_WEBHOOK_URL` | *(Optional)* Slack incoming webhook URL for notifications |
| Variable | `BASE_BRANCH` | Base branch to create PRs against (default: `main`) |
| Variable | `MAX_HEAL_ATTEMPTS` | Max self-healing iterations (default: `3`) |
| Variable | `REGRESSION_GUARD` | Enable test regression detection (default: `true`) |
| Variable | `TEST_COMMAND` | Custom test command, overrides auto-detection (default: empty) |
| Variable | `TEST_SUITE_TIMEOUT` | Timeout in seconds for full test suite (default: `300`) |
| Variable | `MAX_API_RETRIES` | Retry count for transient API errors (default: `3`) |
| Variable | `API_RETRY_DELAY` | Base delay in seconds for retry backoff (default: `2.0`) |

### 4. Enable GitHub Actions

Push this repo to GitHub. The workflow at `.github/workflows/agent.yml` will start running on its 10-minute schedule automatically. You can also trigger it manually from the Actions tab.

### 5. Verify the connection (optional, local only)

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt

# Create config/.env with your credentials
cp config/.env.example config/.env  # then fill in your values

python config/verify.py
```

## Per-Repo Configuration (`.agent.yml`)

Drop an `.agent.yml` file in the root of your **target repo** to customize the agent's behavior per-project. All fields are optional — defaults are shown below:

```yaml
# Branches
base_branch: main

# Pipeline tuning
max_relevant_files: 5       # Max files to include in context
max_heal_attempts: 3        # Self-healing loop iterations
regression_guard: true      # Run before/after test comparison
test_command: null           # Override auto-detected test runner (e.g., "npm test")
test_suite_timeout: 300     # Seconds before test suite times out

# Type checking
type_check:
  enabled: true             # Run tsc / mypy
  blocking: false           # If true, type errors abort the pipeline

# Review passes
review:
  security: true            # Run bandit / Claude security scan
  optimize: true            # Run Claude optimization pass
  seo: true                 # Run SEO/accessibility check (UI files only)
  readme: true              # Auto-update README with changes

# PR reviewers
reviewers:
  users: []                 # GitHub usernames to request review
  teams: []                 # GitHub team slugs to request review

# Label names (customize if defaults conflict)
labels:
  trigger: ai-implement
  processing: ai-processing
  done: ai-done
  failed: ai-failed

# Notifications
notifications:
  slack_webhook: null        # Incoming webhook URL (or use SLACK_WEBHOOK_URL env var)
  on_success: false
  on_failure: true
```

## Usage

1. Go to your **target repo** and create a new issue
2. Write a clear description with **Acceptance Criteria** as a checklist
3. Add the label **`ai-implement`** to the issue
4. The agent picks it up within 10 minutes, runs the pipeline, and comments with the PR link

To trigger immediately without waiting, go to `Actions → AI Coding Agent → Run workflow`.

### Running manually (local)

```bash
# Single issue
python agent/orchestrator.py --issue <issue-number>

# Full daemon mode (processes all pending issues sequentially)
python agent/daemon.py
```

## Project Structure

```
ai-coding-agent/
├── .github/
│   └── workflows/
│       └── agent.yml              # Scheduled GitHub Actions workflow
├── agent/
│   ├── orchestrator.py            # 8-stage pipeline logic
│   ├── daemon.py                  # Sequential issue processor (local/fallback)
│   ├── discover.py                # Finds & claims pending issues (Actions job 1)
│   ├── worker.py                  # Processes a single issue (Actions job 2, matrix)
│   └── tools/
│       ├── task_reader.py         # GitHub issue fetching and parsing
│       ├── code_scanner.py        # Codebase analysis (file tree, search, read)
│       ├── branch_manager.py      # Git branch operations via GitHub API
│       ├── implementer.py         # Multi-file code generation via Claude
│       ├── test_writer.py         # Framework-aware test generation (Jest/pytest)
│       ├── healer.py              # Self-healing loop for failing tests
│       ├── regression_guard.py    # Before/after test suite comparison
│       ├── type_checker.py        # tsc/mypy auto-detection and execution
│       ├── reviewer.py            # Security, optimization, and SEO review
│       └── pr_creator.py          # Commit, push, and PR creation
├── agent/utils/
│   ├── client.py                  # Centralized Anthropic client (singleton)
│   ├── github.py                  # Shared GitHub helpers (get_repo, labels)
│   ├── config.py                  # 3-tier config (defaults → .agent.yml → env)
│   ├── parsing.py                 # Response parsing (code fences, test counts)
│   ├── retry.py                   # Exponential backoff for Anthropic & GitHub APIs
│   ├── examples.py                # Few-shot example store (local + GitHub)
│   ├── notifications.py           # Slack webhook notifications
│   └── summary.py                 # GitHub Actions job summary writer
├── config/
│   ├── .env                       # Local credentials (gitignored)
│   ├── .env.example               # Template for .env
│   └── verify.py                  # Connectivity check script
├── tests/                         # Unit tests (see Contributing)
└── requirements.txt
```

## Tech Stack

- **AI:** Anthropic SDK — Claude Sonnet 4.6
- **Automation:** GitHub Actions (scheduled cron + dynamic matrix)
- **GitHub API:** PyGithub with retry/backoff
- **Resilience:** Exponential backoff for Anthropic & GitHub APIs, self-healing test loop
- **Terminal UI:** Rich
- **Config:** python-dotenv, PyYAML, 3-tier merge
- **Target project tooling:** ESLint, Jest, React Testing Library, Bandit, pytest, mypy, tsc

## Architecture

```
┌─────────────────────────────────────────────┐
│             GitHub Actions (cron)            │
│                                             │
│  ┌──────────┐    ┌──────────┐ ┌──────────┐  │
│  │ discover │───→│ worker 1 │ │ worker 2 │  │
│  └──────────┘    └──────────┘ └──────────┘  │
│       │               │            │        │
│  claims issues   runs pipeline  runs pipeline│
│  via labels      for issue #X   for issue #Y│
└─────────────────────────────────────────────┘
         │                │
         ▼                ▼
┌─────────────────────────────────────────────┐
│              Anthropic Claude API           │
│  (file analysis, implementation, tests,     │
│   healing, security, optimization, PR desc) │
└─────────────────────────────────────────────┘
```

## Notes

- The agent supports **TypeScript/React**, **JavaScript**, and **Python** codebases out of the box. Other stacks can be supported by configuring `test_command` in `.agent.yml`.
- Code scanning caps at 5 relevant files per issue (configurable via `max_relevant_files`) to keep context focused and API costs manageable.
- All AI operations use `claude-sonnet-4-6`.
- The `GH_PAT` token must have `repo` scope on the target repository. The default `GITHUB_TOKEN` provided by Actions only covers the repo where the workflow lives.
- The agent creates one branch per issue (`issue-<number>`). If the branch already exists, it reuses it.
- Slack notifications are opt-in: set `SLACK_WEBHOOK_URL` as a secret and configure `on_success`/`on_failure` in `.agent.yml`.
