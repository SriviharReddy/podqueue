#!/bin/bash
# PodQueue FastAPI & Vanilla JS Setup Script
set -e

echo "PodQueue Setup Script"
echo "====================="
echo

# Get repo root path
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

echo "Creating directories..."
mkdir -p data/downloads data/feeds data/artwork data/logs data/state/channel_checks
echo "✓ Run directories created under ./data"

# Create .env from template if missing
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        # Generate a random session secret
        RAND_SECRET=$(head -c 16 /dev/urandom | xxd -p 2>/dev/null || echo "secret_$(date +%s)")
        sed -i "s/SESSION_SECRET=changeme/SESSION_SECRET=$RAND_SECRET/g" .env
        echo "✓ Created .env file from template (with auto-generated SESSION_SECRET)"
        echo "  IMPORTANT: Update ADMIN_PASSWORD and BASE_URL in the .env file!"
    else
        echo "⚠ Warning: .env.example not found. Creating manual .env placeholder."
        echo "BASE_URL=http://YOUR_SERVER_IP" > .env
        echo "ADMIN_PASSWORD=changeme" >> .env
        echo "SESSION_SECRET=secret_$(date +%s)" >> .env
    fi
else
    echo "✓ .env already exists"
fi

# Create channels.json if missing
if [ ! -f data/channels.json ]; then
    echo "[]" > data/channels.json
    echo "✓ Created empty data/channels.json"
fi

# Create cookies.txt placeholder
if [ ! -f cookies.txt ]; then
    echo "# Place YouTube cookies here" > cookies.txt
    echo "✓ Created cookies.txt placeholder"
fi

# Virtual environment setup
echo
echo "Setting up Python virtual environment..."
if [ ! -d venv ]; then
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate & install dependencies
source venv/bin/activate
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "✓ All Python dependencies installed successfully."

# Check for ffmpeg
if ! command -v ffmpeg &> /dev/null; then
    echo
    echo "⚠ Warning: ffmpeg is not installed or not in PATH."
    echo "  FFmpeg is required for yt-dlp to extract audio to .m4a format."
    echo "  Please install ffmpeg (e.g. 'sudo apt install ffmpeg' on Ubuntu)."
fi

# Systemd unit generation
echo
echo "======================================"
echo "Systemd Service Configuration"
echo "======================================"
SYSTEMD_FILE="/etc/systemd/system/podqueue.service"

read -p "Would you like to install the systemd service unit? (y/n): " INSTALL_SYSTEMD

if [[ "$INSTALL_SYSTEMD" =~ ^[Yy]$ ]]; then
    # Generate systemd file contents
    SYSTEMD_CONTENT="[Unit]
Description=PodQueue Podcast RSS Sync Service
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$REPO_ROOT
ExecStart=$REPO_ROOT/venv/bin/uvicorn podqueue.api.main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=always
RestartSec=1s
Nice=19
IOSchedulingClass=2
IOSchedulingPriority=7

[Install]
WantedBy=multi-user.target"

    echo "Writing systemd service file..."
    echo "$SYSTEMD_CONTENT" | sudo tee "$SYSTEMD_FILE" > /dev/null
    
    echo "Reloading systemd daemon and enabling service..."
    sudo systemctl daemon-reload
    sudo systemctl enable podqueue.service
    
    echo "✓ Systemd service podqueue.service enabled successfully."
    echo "  To start: sudo systemctl start podqueue"
    echo "  To view logs: journalctl -u podqueue -f"
else
    echo "Skipping systemd installation. You can launch manually via:"
    echo "  source venv/bin/activate"
    echo "  uvicorn podqueue.api.main:app --host 0.0.0.0 --port 8000"
fi

echo
echo "======================================"
echo "Setup complete!"
echo "======================================"