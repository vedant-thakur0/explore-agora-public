# Getting Started with AGORA

## What is this?

AGORA is a toolkit that discovers and analyzes AI-related legislation from U.S. Congress. It gives you interactive reports that show which legislators sponsor AI bills, how they form coalitions, how policy topics connect through co-sponsorship, and how bills distribute across different policy areas. You can either generate reports locally or use Claude Code (an AI assistant) to regenerate them or ask questions about the data.

## Two ways to use it

### Option A: Generate reports locally (recommended starting point)
Reports are not bundled with this repository — they are generated locally on demand. To produce a fresh report bundle:
1. Complete the setup steps below (clone or download the repo, add credentials).
2. Open a terminal in the AGORA folder and run `/generate-reports` via Claude Code (or `python3 -m pipeline.cli reports` directly).
3. Open the `reports/generated/<date>/index.html` file that the command prints when it finishes.

### Option B: Operate it with Claude Code (for analysis and updates)
If you want to refresh reports, ask questions about the data, or explore it interactively, you'll use Claude Code to drive the toolkit.

## Setting up (public / self-hosted)

1. **Clone the repository:**
   ```bash
   git clone <repo-url>
   cd agora
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure credentials:**
   ```bash
   cp .env.example .env
   ```
   Then open `.env` and fill in your own keys:
   - `CONGRESS_API_KEY` — free from https://api.congress.gov/sign-up/
   - `ANTHROPIC_API_KEY` — from https://console.anthropic.com/

   Optional (only if using Supabase sync):
   - `SUPABASE_URL` and `SUPABASE_KEY`

   **Important:** Never commit or share the `.env` file. Treat it like a password.

4. **Install Claude Code:**
   Go to https://claude.com/claude-code and follow the setup instructions.

## If a maintainer is provisioning you for a team

Each analyst receives:
- A copy of the repository folder (checked out from source control or shared directly)
- A `.env` file handed over separately (never committed, never posted in shared channels)

**Key rotation and revocation:** When an analyst leaves the team, revoke or rotate all API keys associated with their `.env` file.

## Your first session

Once Claude Code is installed and you have the repo folder with credentials:

1. Open a terminal in the AGORA folder. (On a Mac: right-click the AGORA folder in Finder and choose **Services → New Terminal at Folder**, or open Terminal and drag the folder onto the window.)
2. Type `claude` and press Enter. This opens an interactive Claude session.
3. Type plain-English requests like:
   - "generate the latest reports"
   - "what's the pipeline status?"
   - "explain what the coalitions report shows"
   - "which legislators form cross-party coalitions on AI?"

You can also use these named commands:
- `/generate-reports` — Create fresh reports from the current data (output lands in `reports/generated/<date>/index.html`).
- `/pipeline-status` — Check what data is currently loaded and when it was last updated.
- `/run-ranking` — Re-rank bills by relevance (costs money, will ask for confirmation).
- `/refresh-data` — Pull the latest AGORA dataset release and sync it (costs money, will ask for confirmation).

## Rules of the road

- **Don't edit files in `pipeline/runs/` or `pipeline/agents/`.** Claude uses these for state management.
- **If Claude reports an error:** Copy the error message and open a GitHub issue. Don't try to fix the code yourself.
- **Reports are snapshots.** Always check the date on `index.html` — if it's old and you need fresh data, ask Claude to run `/refresh-data` (with the project maintainer's approval).

## Who to contact

To report bugs or ask questions, open a GitHub issue in this repository.
