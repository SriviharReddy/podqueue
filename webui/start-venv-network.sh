#!/bin/bash
# Start PodQueue Web UI on Linux/macOS (Network Mode) using virtual environment

echo "Starting PodQueue Web UI (Network Mode - Virtual Environment)..."
echo "==========================================================="
echo

# Check if we're in the webui directory
if [ ! -f "app.py" ]; then
    echo "Error: Please run this script from the webui directory."
    echo "Current directory: $(pwd)"
    echo
    read -p "Press Enter to continue..."
    exit 1
fi

# Check if virtual environment exists
if [ ! -f "../venv/bin/activate" ]; then
    echo "Error: Virtual environment not found at ../venv"
    echo "Please create a virtual environment first."
    echo
    read -p "Press Enter to continue..."
    exit 1
fi

echo "Activating virtual environment..."
source ../venv/bin/activate

echo "Starting Streamlit Web UI in network mode..."
echo
echo "To access the Web UI from other devices on your network, use:"
echo "  http://YOUR_SERVER_IP:8501"
echo
echo "To stop the server, press Ctrl+C."
echo

streamlit run app.py --server.address 0.0.0.0 --server.port 8501