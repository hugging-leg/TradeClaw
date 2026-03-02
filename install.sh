#!/usr/bin/env bash
# ============================================================
# TradeClaw — One-Line Install Script
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/BryantSuen/Agent-Trader/main/install.sh | bash
#
# What this script does:
#   1. Check prerequisites (Docker, docker compose)
#   2. Create the tradeclaw/ directory
#   3. Download docker-compose.yml, env.template, and SearXNG config from GitHub
#   4. Create user_data/ directory tree
#   5. Copy env.template → .env
#   6. Start all services via docker compose
# ============================================================

set -euo pipefail

# ---- Configuration ----
REPO="BryantSuen/Agent-Trader"
BRANCH="main"
INSTALL_DIR="tradeclaw"
RAW_BASE="https://raw.githubusercontent.com/${REPO}/${BRANCH}"

# ---- Colors ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ---- Banner ----
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║        TradeClaw — Installer                 ║${NC}"
echo -e "${BOLD}║   LLM Agent Trading System                   ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""

# ============================================================
# Step 0: Check prerequisites
# ============================================================
info "Checking prerequisites..."

if ! command -v docker &>/dev/null; then
    error "Docker is not installed. Please install Docker first: https://docs.docker.com/get-docker/"
fi

# Check for 'docker compose' (v2) or 'docker-compose' (v1)
COMPOSE_CMD=""
if docker compose version &>/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
else
    error "Docker Compose is not installed. Please install it: https://docs.docker.com/compose/install/"
fi

if ! command -v curl &>/dev/null; then
    error "curl is not installed. Please install curl first."
fi

ok "Docker: $(docker --version | head -1)"
ok "Compose: $($COMPOSE_CMD version 2>/dev/null | head -1 || echo "$COMPOSE_CMD")"

# ============================================================
# Step 1: Create install directory
# ============================================================
if [ -d "$INSTALL_DIR" ]; then
    warn "Directory '${INSTALL_DIR}/' already exists."
    read -rp "Overwrite configuration files? (y/N) " answer
    if [[ ! "$answer" =~ ^[Yy]$ ]]; then
        info "Keeping existing files. Only starting services."
        cd "$INSTALL_DIR"
        info "Starting services..."
        $COMPOSE_CMD up -d
        echo ""
        ok "Services started! Visit ${BOLD}http://localhost:8000${NC}"
        exit 0
    fi
fi

info "Creating directory: ${INSTALL_DIR}/"
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# ============================================================
# Step 2: Create user_data directory tree
# ============================================================
info "Creating user_data/ directory tree..."

mkdir -p user_data/logs
mkdir -p user_data/agents
mkdir -p user_data/postgres
mkdir -p searxng

ok "Directory structure created"

# ============================================================
# Step 3: Download files from GitHub
# ============================================================
info "Downloading files from GitHub (${REPO})..."

download() {
    local remote_path="$1"
    local local_path="$2"
    info "  ↓ ${remote_path}"
    if ! curl -fsSL "${RAW_BASE}/${remote_path}" -o "${local_path}"; then
        error "Failed to download ${remote_path}"
    fi
}

# Core files
download "docker-compose.yml"       "docker-compose.yml"
download "docker-compose.dev.yml"   "docker-compose.dev.yml"
download "env.template"             "env.template"

# SearXNG configuration
download "searxng/settings.yml"     "searxng/settings.yml"

ok "All files downloaded"

# ============================================================
# Step 4: Create .env from template
# ============================================================
if [ -f ".env" ]; then
    warn ".env already exists, not overwriting."
    warn "If you want a fresh .env, delete it and run this script again."
else
    info "Creating .env from env.template..."
    cp env.template .env

    # Generate a random JWT secret
    JWT_SECRET=$(openssl rand -hex 32 2>/dev/null || head -c 64 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 64)
    if [[ -n "$JWT_SECRET" ]]; then
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' "s/JWT_SECRET_KEY=CHANGE-ME-TO-A-RANDOM-STRING/JWT_SECRET_KEY=${JWT_SECRET}/" .env
        else
            sed -i "s/JWT_SECRET_KEY=CHANGE-ME-TO-A-RANDOM-STRING/JWT_SECRET_KEY=${JWT_SECRET}/" .env
        fi
        ok "Generated random JWT_SECRET_KEY"
    fi

    ok ".env created — please edit it with your API keys"
fi

# ============================================================
# Step 5: Display summary & prompt for configuration
# ============================================================
echo ""
echo -e "${BOLD}════════════════════════════════════════════════${NC}"
echo -e "${BOLD}  Installation complete!${NC}"
echo -e "${BOLD}════════════════════════════════════════════════${NC}"
echo ""
echo -e "  Directory:  ${CYAN}$(pwd)${NC}"
echo ""
echo -e "  ${BOLD}Directory structure:${NC}"
echo "  tradeclaw/"
echo "  ├── docker-compose.yml"
echo "  ├── docker-compose.dev.yml"
echo "  ├── .env                    ← Edit this!"
echo "  ├── env.template"
echo "  ├── searxng/"
echo "  │   └── settings.yml"
echo "  └── user_data/"
echo "      ├── agents/"
echo "      ├── logs/"
echo "      └── postgres/"
echo ""
echo -e "  ${BOLD}Next steps:${NC}"
echo ""
echo -e "  1. Edit your API keys:"
echo -e "     ${CYAN}cd ${INSTALL_DIR} && nano .env${NC}"
echo ""
echo -e "     At minimum, configure:"
echo -e "     • ${YELLOW}ALPACA_API_KEY${NC} / ${YELLOW}ALPACA_SECRET_KEY${NC} (broker)"
echo -e "     • ${YELLOW}TIINGO_API_KEY${NC} (market data)"
echo -e "     • ${YELLOW}LLM_API_KEY${NC} / ${YELLOW}LLM_BASE_URL${NC} / ${YELLOW}LLM_MODEL${NC} (AI model)"
echo ""
echo -e "  2. Start all services:"
echo -e "     ${CYAN}cd ${INSTALL_DIR} && ${COMPOSE_CMD} up -d${NC}"
echo ""
echo -e "  3. Open the dashboard:"
echo -e "     ${CYAN}http://localhost:8000${NC}"
echo ""
echo -e "  4. View logs:"
echo -e "     ${CYAN}${COMPOSE_CMD} logs -f trading-agent${NC}"
echo ""

# ============================================================
# Step 6: Optionally start services
# ============================================================
read -rp "Start services now? (y/N) " start_answer
if [[ "$start_answer" =~ ^[Yy]$ ]]; then
    info "Pulling Docker images (this may take a few minutes on first run)..."
    $COMPOSE_CMD pull
    info "Starting services..."
    $COMPOSE_CMD up -d
    echo ""
    ok "All services started!"
    echo ""
    echo -e "  Dashboard:  ${CYAN}http://localhost:8000${NC}"
    echo -e "  Logs:       ${CYAN}${COMPOSE_CMD} logs -f trading-agent${NC}"
    echo -e "  Stop:       ${CYAN}${COMPOSE_CMD} down${NC}"
    echo ""
else
    info "Skipping service startup."
    echo -e "  When ready, run: ${CYAN}cd ${INSTALL_DIR} && ${COMPOSE_CMD} up -d${NC}"
    echo ""
fi

echo -e "${GREEN}Done! Happy trading 🚀${NC}"
