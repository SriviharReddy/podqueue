#!/bin/bash
# PodQueue Setup Script for Linux/macOS
# This script will set up the entire PodQueue environment including the Web UI

set -e  # Exit on error

echo "PodQueue Setup Script for Linux/macOS"
echo "======================================"
echo

# Get the script directory (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if we're in the correct directory
if [ ! -d "scripts" ]; then
    echo "Error: Please run this script from the root of the PodQueue repository."
    echo "Current directory: $(pwd)"
    echo
    echo "Make sure you've cloned the repository and navigate to the project directory before running this script."
    exit 1
fi

echo "Checking for required tools..."
echo

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed or not in PATH."
    echo "Please install Python 3 from https://www.python.org/downloads/"
    exit 1
else
    PYTHON_VERSION=$(python3 --version)
    echo "✓ Found $PYTHON_VERSION"
fi

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "Error: pip3 is not installed."
    echo "Please install pip or upgrade Python."
    exit 1
else
    PIP_VERSION=$(pip3 --version)
    echo "✓ Found $PIP_VERSION"
fi

echo
echo "Creating Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
source venv/bin/activate

echo
echo "Installing dependencies from requirements.txt..."
pip3 install --upgrade pip
pip3 install -r scripts/requirements.txt
if [ $? -ne 0 ]; then
    echo "Error: Failed to install dependencies."
    exit 1
fi
echo "✓ Dependencies installed"

echo
echo "Checking for required system tools..."
echo

# Check if yt-dlp is installed (will also be in venv)
if ! command -v yt-dlp &> /dev/null; then
    echo "⚠ Warning: yt-dlp is not installed or not in PATH."
    echo "  It will be installed in the virtual environment."
else
    YTDLP_VERSION=$(yt-dlp --version)
    echo "✓ Found yt-dlp version $YTDLP_VERSION"
fi

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo "⚠ Warning: jq is not installed or not in PATH."
    echo "  Install with: sudo apt install jq  (or equivalent for your OS)"
    echo "  The downloader script requires jq to work."
else
    JQ_VERSION=$(jq --version)
    echo "✓ Found jq version $JQ_VERSION"
fi

# Check if ffmpeg is installed
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠ Warning: ffmpeg is not installed or not in PATH."
    echo "  Install with: sudo apt install ffmpeg  (or equivalent for your OS)"
    echo "  Audio conversion requires ffmpeg."
else
    FFMPEG_VERSION=$(ffmpeg -version | head -1)
    echo "✓ Found $FFMPEG_VERSION"
fi

echo
echo "Creating channels.json file if it doesn't exist..."
if [ ! -f "scripts/channels.json" ]; then
    if [ -f "scripts/channels.json.example" ]; then
        cp "scripts/channels.json.example" "scripts/channels.json"
        echo "✓ Created scripts/channels.json from example file."
    else
        echo "⚠ Warning: scripts/channels.json.example not found."
        echo "  You will need to create scripts/channels.json manually."
    fi
else
    echo "✓ scripts/channels.json already exists."
fi

echo
echo "Creating cookies.txt placeholder..."
if [ ! -f "cookies.txt" ]; then
    echo "# Place your YouTube cookies.txt file here" > cookies.txt
    echo "✓ Created cookies.txt placeholder"
    echo "  IMPORTANT: Export cookies from YouTube for best results!"
    echo "  See README.md for instructions."
else
    echo "✓ cookies.txt already exists."
fi

echo
echo "======================================"
echo "Setup complete!"
echo "======================================"
echo
echo "Next steps:"
echo "  1. Export YouTube cookies (recommended):"
echo "     - Install 'Get cookies.txt locally' Chrome extension"
echo "     - Log into YouTube and export cookies"
echo "     - Replace cookies.txt with the exported file"
echo
echo "  2. Configure channels:"
echo "     - Edit scripts/channels.json with your YouTube channels"
echo "     - Or use the Web UI to add channels"
echo
echo "  3. Start the Web UI:"
echo "     ./webui/start.sh"
echo
echo "  4. Open your browser to:"
echo "     http://localhost:8501"
echo
echo "======================================"