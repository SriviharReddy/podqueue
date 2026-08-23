import os
import pytest
from unittest.mock import patch, MagicMock
from podqueue.core.job_runner import is_supervised, update_ytdlp

def test_is_supervised_detection():
    # Unsupervised default
    with patch.dict(os.environ, {}, clear=True):
        assert is_supervised() is False
        
    # Systemd INVOCATION_ID
    with patch.dict(os.environ, {"INVOCATION_ID": "systemd-unit-1234"}, clear=True):
        assert is_supervised() is True
        
    # Systemd JOURNAL_STREAM
    with patch.dict(os.environ, {"JOURNAL_STREAM": "8:12345"}, clear=True):
        assert is_supervised() is True
        
    # Explicit env flag
    with patch.dict(os.environ, {"AUTO_RESTART_ON_UPDATE": "true"}, clear=True):
        assert is_supervised() is True
        
    with patch.dict(os.environ, {"AUTO_RESTART_ON_UPDATE": "1"}, clear=True):
        assert is_supervised() is True

def test_update_ytdlp_unsupervised():
    """Verify that update_ytdlp does not call os._exit when unsupervised."""
    with patch.dict(os.environ, {}, clear=True), \
         patch("subprocess.run") as mock_subproc, \
         patch("os._exit") as mock_exit:
        
        mock_subproc.return_value = MagicMock(returncode=0, stdout="Successfully installed yt-dlp")
        
        update_ytdlp()
        
        assert mock_subproc.called
        assert mock_exit.called is False

def test_update_ytdlp_supervised():
    """Verify that update_ytdlp calls os._exit(0) when running under systemd."""
    with patch.dict(os.environ, {"INVOCATION_ID": "systemd-123"}, clear=True), \
         patch("subprocess.run") as mock_subproc, \
         patch("time.sleep"), \
         patch("os._exit") as mock_exit:
        
        mock_subproc.return_value = MagicMock(returncode=0, stdout="Successfully installed yt-dlp")
        
        update_ytdlp()
        
        assert mock_subproc.called
        mock_exit.assert_called_once_with(0)

def test_update_ytdlp_failure_raises():
    """Verify that a non-zero exit code raises RuntimeError."""
    with patch.dict(os.environ, {}, clear=True), \
         patch("subprocess.run") as mock_subproc:
        
        mock_subproc.return_value = MagicMock(returncode=1, stdout="pip install error")
        
        with pytest.raises(RuntimeError, match="pip install failed with exit code 1"):
            update_ytdlp()
