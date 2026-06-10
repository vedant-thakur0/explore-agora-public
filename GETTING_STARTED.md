# Getting Started with AGORA

## What is this?

AGORA is a toolkit that discovers and analyzes AI-related legislation from U.S. Congress. It gives you interactive reports that show which legislators sponsor AI bills, how they form coalitions, how policy topics connect through co-sponsorship, and how bills distribute across different policy areas. You can either read existing reports or use Claude Code (an AI assistant) to regenerate them or ask questions about the data.

## Two ways to use it

### Option A: Just read the reports (no setup needed)
1. Ask Vedant for access to the shared drive folder containing the latest reports.
2. Open the `index.html` file from the most recent dated folder.
3. Browse the interactive charts and analysis — no software installation required.

### Option B: Operate it with Claude Code (for analysis and updates)
If you want to refresh reports, ask questions about the data, or explore it interactively, you'll use Claude Code to drive the toolkit.

## Setting up Claude Code

1. **Install Claude Code:** Go to https://claude.com/claude-code and follow the setup instructions.
2. **Get the repo folder:** Ask Vedant for a copy of the AGORA repository folder. Download or copy it to your local computer.
3. **Get the `.env` file:** Ask Vedant directly (email or Slack) for the `.env` file that contains API credentials. Place this file in the root of your AGORA folder.
   - **Important:** Never create API accounts yourself. Never share or email the `.env` file with anyone else. Treat it like a password.

## Your first session

Once Claude Code is installed and you have the repo folder locally:

1. Open a terminal in the AGORA folder.
2. Type `claude` and press Enter. This opens an interactive Claude session.
3. Type plain-English requests like:
   - "generate the latest reports"
   - "what's the pipeline status?"
   - "explain what the coalitions report shows"
   - "which legislators form cross-party coalitions on AI?"

You can also use these named commands:
- `/generate-reports` — Create fresh reports from the current data.
- `/pipeline-status` — Check what data is currently loaded and when it was last updated.
- `/run-ranking` — Re-rank bills by relevance (costs money, will ask for confirmation).
- `/refresh-data` — Pull the latest AGORA dataset release and sync it (costs money, will ask for confirmation).

## Rules of the road

- **Don't edit files in `pipeline/runs/` or `pipeline/agents/`.** Claude uses these for state management.
- **If Claude reports an error:** Copy the error message and send it to Vedant. Don't try to fix the code yourself.
- **Reports are snapshots.** Always check the date on `index.html` — if it's old and you need fresh data, ask Claude to run `/refresh-data` (with Vedant's approval).

## Who to contact

**Vedant Thakur** — Maintainer. Email: vedantt2210@gmail.com
