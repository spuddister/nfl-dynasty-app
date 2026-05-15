# Fantasy AI

Your personal dynasty fantasy football assistant. It pulls live data from Sleeper, checks injury reports, searches Reddit for player buzz, and gives you clear recommendations — no spreadsheets required.

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

**4. Optional: Reddit credentials**

Reddit lets the assistant search for live player sentiment, injury buzz, and waiver chatter on r/dynastyff and r/fantasyfootball. Without it the assistant still works — it just skips Reddit.

1. Go to [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) → **create another app** → choose **script**
2. Add to `.env`:

```
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
```

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

Checks injuries, Sleeper trending adds, and Reddit, then tells you exactly who to start and who to pick up.

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

A deeper dive into the rookie class using Reddit buzz, KTC dynasty values, and landing spot analysis. Use `draft-board` for the ranked board; use this for the "why" behind each prospect.

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

If you'd rather not edit `.env` by hand, this walks you through setting your API keys.

```bash
uv run fantasy setup
```

---

## Tips

- **Run `roster-review` once a week** — it's the most comprehensive command and gives you a full action checklist.
- **Run `draft-board` on draft day** — re-run it after each pick to see updated availability.
- **Use `ask` for one-off questions** — it has full access to your roster and all the same tools.
- All data is cached locally (KTC values for 24h, injury reports for 2h) so repeat runs are fast.
