#!/bin/bash
# Start PodQueue Web UI on Linux/macOS

echo "Starting PodQueue Web UI..."
echo "========================"
echo

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check if we're in the webui directory
if [ ! -f "app.py" ]; then
    echo "Error: Please run this script from the webui directory."
    echo "Current directory: $(pwd)"
    echo
    read -p "Press Enter to continue..."
    exit 1
fi

echo "Starting Streamlit Web UI..."
echo
echo "Once the server starts, open your browser and go to:"
echo "  http://localhost:8501"
echo
echo "To stop the server, press Ctrl+C."
echo

streamlit run app.py