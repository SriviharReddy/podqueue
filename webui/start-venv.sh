#!/bin/bash
# Start PodQueue Web UI on Linux/macOS using virtual environment

echo "Starting PodQueue Web UI (Virtual Environment)..."
echo "============================================="
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

echo "Starting Streamlit Web UI..."
echo
echo "Once the server starts, open your browser and go to:"
echo "  http://localhost:8501"
echo
echo "To stop the server, press Ctrl+C."
echo

streamlit run app.py