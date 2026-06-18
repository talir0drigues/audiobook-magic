#!/bin/bash
# Double-click this file on macOS to launch Audiobook Downloader.
# It will auto-install uv and FFmpeg if they are not already present.

cd "$(dirname "$0")"

YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo "=== Audiobook Downloader ==="
echo ""

# --- uv ---
if ! command -v uv &>/dev/null; then
    echo -e "${YELLOW}Installing uv (Python manager)...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

if ! command -v uv &>/dev/null; then
    echo -e "${RED}Could not install uv. Please install it manually: https://docs.astral.sh/uv/${NC}"
    read -rp "Press Enter to close..."
    exit 1
fi

# --- FFmpeg ---
if ! command -v ffmpeg &>/dev/null; then
    echo -e "${YELLOW}FFmpeg not found.${NC}"
    if command -v brew &>/dev/null; then
        echo -e "${YELLOW}Installing FFmpeg via Homebrew...${NC}"
        brew install ffmpeg
    else
        echo -e "${RED}Homebrew not found. Installing Homebrew first...${NC}"
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        brew install ffmpeg
    fi
fi

if ! command -v ffmpeg &>/dev/null; then
    echo -e "${RED}Could not install FFmpeg. Please install it manually: https://ffmpeg.org/${NC}"
    read -rp "Press Enter to close..."
    exit 1
fi

# --- Run ---
uv run main.py

echo ""
read -rp "Press Enter to close..."
