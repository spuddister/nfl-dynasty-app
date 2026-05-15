#!/usr/bin/env bash
# Fantasy AI — startup script
# Installs dependencies, sets up .env, then shows available commands.

set -euo pipefail

BOLD='\033[1m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "\n${BOLD}${CYAN}╔══════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║       Fantasy AI — Dynasty Advisor    ║${RESET}"
echo -e "${BOLD}${CYAN}║   Washington Football League (2026)   ║${RESET}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════╝${RESET}\n"

# ── 1. Check Python ───────────────────────────────────────────────────────────
echo -e "${BOLD}[1/4] Checking Python...${RESET}"
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}Python 3 not found. Install it from https://python.org${RESET}"
    exit 1
fi
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo -e "  ${GREEN}✓ Python ${PYTHON_VERSION}${RESET}"

# ── 2. Install uv (fast Python package manager) ───────────────────────────────
echo -e "\n${BOLD}[2/4] Checking uv package manager...${RESET}"
if ! command -v uv &>/dev/null; then
    echo -e "  ${YELLOW}uv not found — installing...${RESET}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Try to reload PATH
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        echo -e "  ${YELLOW}uv installed but not on PATH yet.${RESET}"
        echo -e "  Run: ${BOLD}source ~/.bashrc && ./start.sh${RESET}"
        exit 1
    fi
fi
echo -e "  ${GREEN}✓ uv $(uv --version 2>/dev/null | head -1)${RESET}"

# ── 3. Install Python dependencies ───────────────────────────────────────────
echo -e "\n${BOLD}[3/4] Installing dependencies...${RESET}"
uv sync --quiet
echo -e "  ${GREEN}✓ Dependencies installed${RESET}"

# ── 4. Configure .env ────────────────────────────────────────────────────────
echo -e "\n${BOLD}[4/4] Checking configuration...${RESET}"

if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "  ${YELLOW}Created .env from .env.example${RESET}"
    else
        touch .env
    fi
fi

# Check for Google API key
GOOGLE_KEY=$(grep -E '^GOOGLE_API_KEY=' .env | cut -d= -f2- | tr -d '"' | tr -d "'")
if [ -z "$GOOGLE_KEY" ]; then
    echo -e "\n  ${YELLOW}Google Gemini API key not set.${RESET}"
    echo -e "  Get a FREE key at: ${BOLD}https://aistudio.google.com${RESET} → Get API key"
    printf "  Enter your Google API key: "
    read -r API_KEY
    if [ -n "$API_KEY" ]; then
        if grep -q '^GOOGLE_API_KEY=' .env; then
            sed -i "s|^GOOGLE_API_KEY=.*|GOOGLE_API_KEY=${API_KEY}|" .env
        else
            echo "GOOGLE_API_KEY=${API_KEY}" >> .env
        fi
        echo -e "  ${GREEN}✓ API key saved to .env${RESET}"
    else
        echo -e "  ${RED}No key entered — AI commands won't work until key is added.${RESET}"
    fi
else
    echo -e "  ${GREEN}✓ Google Gemini API key configured${RESET}"
fi

# Check Reddit (optional)
REDDIT_ID=$(grep -E '^REDDIT_CLIENT_ID=' .env | cut -d= -f2- | tr -d '"')
if [ -z "$REDDIT_ID" ]; then
    echo -e "  ${YELLOW}⚠  Reddit not configured (optional — enables live player sentiment)${RESET}"
    echo -e "     Run ${BOLD}uv run fantasy setup${RESET} to add Reddit credentials."
fi

# ── Done — show menu ──────────────────────────────────────────────────────────
echo -e "\n${GREEN}${BOLD}Setup complete!${RESET}\n"
echo -e "${BOLD}Available commands:${RESET}"
echo -e ""
echo -e "  ${CYAN}uv run fantasy analyze-roster${RESET}   Full dynasty tier analysis of your team"
echo -e "  ${CYAN}uv run fantasy draft-board${RESET}      Rookie draft board (updates as picks are made)"
echo -e "  ${CYAN}uv run fantasy roster-review${RESET}    Deep weekly roster + dynasty strategy review"
echo -e "  ${CYAN}uv run fantasy weekly${RESET}           Quick start/sit + waiver wire targets"
echo -e "  ${CYAN}uv run fantasy trade${RESET}            Evaluate a trade offer"
echo -e "  ${CYAN}uv run fantasy rookies${RESET}          Scout the rookie class (qualitative)"
echo -e "  ${CYAN}uv run fantasy ask \"...\"${RESET}        Ask anything about your team"
echo -e ""
echo -e "${BOLD}League info:${RESET}"
echo -e "  Platform: Sleeper — Washington Football League (2026)"
echo -e "  Format:   Dynasty | Full PPR | SUPER_FLEX (2QB)"
echo -e "  Rookie draft: May 15, 2026 — you pick 7th (4 rounds)"
echo -e ""
echo -e "  ${YELLOW}Tip: Start with${RESET} ${BOLD}${CYAN}uv run fantasy draft-board${RESET} ${YELLOW}to prep for your May 15 draft.${RESET}"

# If a command was passed as argument, run it
if [ $# -gt 0 ]; then
    echo -e "\n${BOLD}Running: fantasy $*${RESET}\n"
    uv run fantasy "$@"
fi
