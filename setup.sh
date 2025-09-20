#!/bin/bash
# PodQueue Setup Script for Linux/macOS
# This script will set up the entire PodQueue environment including the Web UI

echo "PodQueue Setup Script for Linux/macOS"
echo "===================================="
echo

# Check if we're in the correct directory
if [ ! -d "scripts" ]; then
    echo "Error: Please run this script from the root of the PodQueue repository."
    echo "Current directory: $(pwd)"
    echo
    echo "Make sure you've cloned the repository and navigate to the project directory before running this script."
    echo
    read -p "Press Enter to continue..."
    exit 1
fi

echo "Checking for required tools..."
echo

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed or not in PATH."
    echo "Please install Python 3 from https://www.python.org/downloads/"
    echo
    read -p "Press Enter to continue..."
    exit 1
else
    PYTHON_VERSION=$(python3 --version)
    echo "Found $PYTHON_VERSION"
fi

# Check if pip is installed
if ! command -v pip3 &> /dev/null; then
    echo "Error: pip3 is not installed."
    echo "Please install pip or upgrade Python."
    echo
    read -p "Press Enter to continue..."
    exit 1
else
    PIP_VERSION=$(pip3 --version)
    echo "Found $PIP_VERSION"
fi

echo
echo "Installing main dependencies..."
pip3 install -r scripts/requirements.txt
if [ $? -ne 0 ]; then
    echo "Error: Failed to install main dependencies."
    echo
    read -p "Press Enter to continue..."
    exit 1
fi

echo
echo "Installing Web UI dependencies..."
pip3 install -r webui/requirements.txt
if [ $? -ne 0 ]; then
    echo "Error: Failed to install Web UI dependencies."
    echo
    read -p "Press Enter to continue..."
    exit 1
fi

echo
echo "Checking for required system tools..."
echo

# Check if yt-dlp is installed
if ! command -v yt-dlp &> /dev/null; then
    echo "Warning: yt-dlp is not installed or not in PATH."
    echo "Please install yt-dlp from https://github.com/yt-dlp/yt-dlp#installation"
    echo "The Web UI will not be able to convert @username URLs without yt-dlp."
    echo
else
    YTDLP_VERSION=$(yt-dlp --version)
    echo "Found yt-dlp version $YTDLP_VERSION"
fi

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo "Warning: jq is not installed or not in PATH."
    echo "Please install jq from https://stedolan.github.io/jq/"
    echo "The downloader script will not work without jq."
    echo
else
    JQ_VERSION=$(jq --version)
    echo "Found jq version $JQ_VERSION"
fi

echo
echo "Creating channels.json file if it doesn't exist..."
if [ ! -f "scripts/channels.json" ]; then
    cp "scripts/channels.json.example" "scripts/channels.json"
    echo "Created scripts/channels.json from example file."
else
    echo "scripts/channels.json already exists."
fi

echo
echo "Setup complete!"
echo "=============="
echo
echo "To start the Web UI, run:"
echo "  ./webui/start.sh"
echo
echo "Or manually run:"
echo "  cd webui"
echo "  streamlit run app.py"
echo
echo "After starting the Web UI, open your browser and go to:"
echo "  http://localhost:8501"
echo
read -p "Press Enter to continue..."