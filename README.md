# AI Coding Agent

An autonomous AI agent that reads GitHub issues and implements them end-to-end — creating a feature branch, writing code, generating tests, running a review, and opening a pull request.

## How It Works

The agent runs a 7-stage pipeline for a given GitHub issue number:

| Stage | What it does |
|-------|-------------|
| 1. Task Reading | Fetches the GitHub issue and extracts title, description, and acceptance criteria |
| 2. Branch Creation | Creates a feature branch from the base branch |
| 3. Code Analysis | Scans the codebase and identifies the most relevant files |
| 4. Implementation | Uses Claude to design and apply code changes |
| 5. Test Writing | Generates Jest + React Testing Library tests |
| 6. Review | Runs security scans, optimization checks, and SEO/accessibility analysis |
| 7. PR Creation | Commits, pushes, and opens a pull request with an auto-generated description |

## Requirements

- Python 3.14+
- An Anthropic API key
- A GitHub personal access token (with `repo` scope)
- A local clone of the target GitHub repository

## Setup

**1. Clone this repo and create a virtual environment:**

```bash
git clone <this-repo-url>
cd ai-coding-agent
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

**2. Create `config/.env`:**

```env
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...
GITHUB_REPO=owner/repo-name
REPO_LOCAL_PATH=C:\path\to\local\clone
BASE_BRANCH=main
```

**3. Verify the connection:**

```bash
python config/verify.py
```

This checks that both the Anthropic API and GitHub API are reachable and correctly configured.

## Usage

```bash
python agent/orchestrator.py --issue <issue-number>
```

**Example:**

```bash
python agent/orchestrator.py --issue 18
```

The agent will run through all 7 stages and print progress to the terminal using Rich formatting. On success, it prints the URL of the newly created pull request.

## Project Structure

```
ai-coding-agent/
├── agent/
│   ├── orchestrator.py       # Entry point — drives the 7-stage pipeline
│   └── tools/
│       ├── task_reader.py    # GitHub issue fetching and parsing
│       ├── code_scanner.py   # Codebase analysis (file tree, search, read)
│       ├── branch_manager.py # Git branch operations
│       ├── implementer.py    # Code generation via Claude
│       ├── test_writer.py    # Jest test generation
│       ├── reviewer.py       # Security, optimization, and SEO review
│       └── pr_creator.py     # Commit, push, and PR creation
├── config/
│   ├── .env                  # Credentials and repo config (not committed)
│   └── verify.py             # Connectivity check script
└── tests/                    # Test directory
```

Each tool module is self-contained and includes a `__main__` block for standalone testing.

## Tech Stack

- **AI:** Anthropic SDK — Claude Sonnet 4.6
- **GitHub:** PyGithub
- **Terminal UI:** Rich
- **Config:** python-dotenv
- **Target project tooling:** ESLint, Jest, React Testing Library, Bandit

## Notes

- The agent is designed for TypeScript/React codebases but can be adapted for other stacks.
- Code scanning caps at 5 relevant files per issue to keep context focused.
- All AI operations use `claude-sonnet-4-6`.
