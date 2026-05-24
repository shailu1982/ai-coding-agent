# AI Coding Agent

An autonomous AI agent that watches your GitHub issues and implements them end-to-end — no human intervention required. Label an issue `ai-implement`, walk away, and the agent creates a branch, writes code, generates tests, runs a review, and opens a pull request.

## How It Works

```
You label an issue "ai-implement"
        ↓
GitHub Actions runs every 10 minutes
        ↓
Daemon picks up the issue, marks it "ai-processing"
        ↓
7-stage pipeline runs autonomously
        ↓
Issue labeled "ai-done" + comment with PR link
```

### The 7-Stage Pipeline

| Stage | What it does |
|-------|-------------|
| 1. Task Reading | Fetches the issue and extracts title, description, and acceptance criteria |
| 2. Branch Creation | Creates a feature branch from the base branch |
| 3. Code Analysis | Scans the codebase and identifies the most relevant files |
| 4. Implementation | Uses Claude to design and apply code changes |
| 5. Test Writing | Generates Jest + React Testing Library tests |
| 6. Review | Runs security scans, optimization checks, and SEO/accessibility analysis |
| 7. PR Creation | Commits, pushes, and opens a pull request with an auto-generated description |

### Issue Label State Machine

| Label | Meaning |
|-------|---------|
| `ai-implement` | Queued — agent will pick this up on the next run |
| `ai-processing` | In progress — pipeline is currently running |
| `ai-done` | Complete — PR link is in the issue comments |
| `ai-failed` | Failed — error details are in the issue comments; remove this label and re-add `ai-implement` to retry |

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
| Secret | `GH_PAT` | Your personal access token |
| Secret | `ANTHROPIC_API_KEY` | Your Anthropic API key (`sk-ant-...`) |
| Secret | `TARGET_REPO` | The repo the agent should work on (`owner/repo-name`) |
| Variable | `BASE_BRANCH` | Base branch to create PRs against (defaults to `main`) |

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

## Usage

1. Go to your **target repo** and create a new issue
2. Add the label **`ai-implement`** to the issue
3. That's it — the agent picks it up within 10 minutes, runs the pipeline, and comments on the issue with the PR link

To trigger immediately without waiting, go to `Actions → AI Coding Agent → Run workflow`.

### Running manually (local)

```bash
python agent/orchestrator.py --issue <issue-number>
```

## Project Structure

```
ai-coding-agent/
├── .github/
│   └── workflows/
│       └── agent.yml         # Scheduled GitHub Actions workflow (every 10 min)
├── agent/
│   ├── daemon.py             # Polls GitHub for labeled issues, drives the pipeline
│   ├── orchestrator.py       # 7-stage pipeline logic
│   └── tools/
│       ├── task_reader.py    # GitHub issue fetching and parsing
│       ├── code_scanner.py   # Codebase analysis (file tree, search, read)
│       ├── branch_manager.py # Git branch operations
│       ├── implementer.py    # Code generation via Claude
│       ├── test_writer.py    # Jest test generation
│       ├── reviewer.py       # Security, optimization, and SEO review
│       └── pr_creator.py     # Commit, push, and PR creation
├── config/
│   ├── .env                  # Local credentials (not committed)
│   └── verify.py             # Connectivity check script
└── requirements.txt
```

## Tech Stack

- **AI:** Anthropic SDK — Claude Sonnet 4.6
- **Automation:** GitHub Actions (scheduled cron workflow)
- **GitHub:** PyGithub
- **Terminal UI:** Rich
- **Config:** python-dotenv
- **Target project tooling:** ESLint, Jest, React Testing Library, Bandit

## Notes

- The agent is designed for TypeScript/React codebases but can be adapted for other stacks.
- Code scanning caps at 5 relevant files per issue to keep context focused.
- All AI operations use `claude-sonnet-4-6`.
- The `GH_PAT` token must have `repo` scope on the target repository. The default `GITHUB_TOKEN` provided by Actions only covers the repo where the workflow lives.
