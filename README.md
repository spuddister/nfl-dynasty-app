# Fantasy AI

Your personal dynasty fantasy football assistant. It pulls live data from Sleeper, checks injury reports, looks up KTC dynasty values, and gives you clear recommendations — no spreadsheets required.

---

## Setup

### Option A — One-step setup (recommended)

```bash
cd fantasy-program
./start.sh
```

This script installs uv (if needed), installs all dependencies, prompts you for your Google API key, and prints every available command. Run it once and you're ready.

### Option B — Manual setup

**1. Install uv (fast Python package manager)**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

After installing, open a new terminal (or run `source ~/.bashrc`) so `uv` is on your PATH.

**2. Install dependencies**

```bash
cd fantasy-program
uv sync
```

**3. Add your Google Gemini API key**

Get a free key at [aistudio.google.com](https://aistudio.google.com) → click **Get API key**.

Open `.env` (already exists in the project) and paste your key:

```
GOOGLE_API_KEY=your_key_here
```

The Sleeper league settings are already pre-filled — you only need the Google key.

---

## Running commands

All commands use `uv run fantasy` from inside the `fantasy-program` folder. You do not need to activate a virtual environment.

---

### `uv run fantasy ask`
**Ask anything about your team or the NFL.**

```bash
uv run fantasy ask "Should I start Jaylen Waddle or Tee Higgins this week?"
uv run fantasy ask "Is Anthony Richardson worth keeping on IR?"
uv run fantasy ask "Who should I target in a trade to improve my RB room?"
```

---

### `uv run fantasy analyze-roster`
**Full dynasty analysis of your entire roster.**

Grades every player on your team (Elite → Drop), flags who to hold, sell, or trade for, and gives you an overall team grade. Run this when you want the big picture.

```bash
uv run fantasy analyze-roster
```

---

### `uv run fantasy weekly`
**Start/sit decisions and waiver wire targets for the current week.**

Checks injuries and Sleeper trending adds, then tells you exactly who to start and who to pick up.

```bash
uv run fantasy weekly                # current week
uv run fantasy weekly --week 8       # specific week
```

---

### `uv run fantasy roster-review`
**Deeper weekly report — more detail than `weekly`.**

Covers everything `weekly` does, plus a dynasty hold/sell check on every starter, trade opportunities, and a numbered to-do checklist of exactly what to do in Sleeper before the week locks.

```bash
uv run fantasy roster-review
uv run fantasy roster-review --week 8
```

---

### `uv run fantasy propose-trade`
**Generate trade proposals you should send to maximize your dynasty team.**

Scans all 9 opponent rosters, pulls KTC dynasty values for every player in the league, checks the injury report for sell-high opportunities, and reviews recent trade history to understand which teams are willing to deal. Outputs 3 concrete proposals — one per best trading partner — each slightly favorable to you but structured to be genuinely appealing to the other team.

```bash
uv run fantasy propose-trade                       # find the top 3 deals across all teams
uv run fantasy propose-trade --team Rickdaddy47    # target a specific opponent
```

This command makes a single Gemini API call (all data is pre-fetched in Python), so it runs fast and doesn't hit rate limits.

---

### `uv run fantasy draft-board`
**Rookie draft board with live availability.**

Shows all incoming rookies ranked and scored for your league (Full PPR + SuperFlex), cross-referenced against picks already made in the draft. Re-run it mid-draft to see who's still available.

Also runs a full Gemini strategy analysis — who to target at each of your 4 picks (slots 7, 17, 27, 37).

```bash
uv run fantasy draft-board
```

---

### `uv run fantasy rookies`
**Qualitative rookie class scouting.**

A deeper dive into the rookie class using KTC dynasty values and landing spot analysis. Use `draft-board` for the ranked board; use this for the "why" behind each prospect.

```bash
uv run fantasy rookies
```

---

### `uv run fantasy trade`
**Evaluate a trade offer.**

Walks you through entering both sides of a trade, checks KTC dynasty values for every player, and gives you a clear ACCEPT / REJECT / COUNTER verdict with reasoning.

```bash
uv run fantasy trade
```

You'll be prompted to enter each player's name, position, NFL team, and age. Type `done` when you've entered all players on each side.

---

### `uv run fantasy setup`
**Interactive wizard to configure your `.env` file.**

If you'd rather not edit `.env` by hand, this walks you through setting your Google API key.

```bash
uv run fantasy setup
```

---

## Tips

- **Run `roster-review` once a week** — it's the most comprehensive command and gives you a full action checklist.
- **Run `draft-board` on draft day** — re-run it after each pick to see updated availability.
- **Use `propose-trade` after `analyze-roster`** — once you know your sell-high candidates, let the AI find the right target.
- **Use `ask` for one-off questions** — it has full access to your roster and all the same tools.
- All data is cached locally (KTC values for 24h, injury reports for 2h) so repeat runs are fast.
