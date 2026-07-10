import { API } from './api.js';

const logConsole = document.getElementById('log-console');
const logStatusDot = document.getElementById('log-status-dot');
const systemStateLabel = document.getElementById('system-state-label');
const lastJobName = document.getElementById('last-job-name');
const lastJobCode = document.getElementById('last-job-code');

const runSyncBtn = document.getElementById('run-sync-btn');
const runRssBtn = document.getElementById('run-rss-btn');
const updateYtdlpBtn = document.getElementById('update-ytdlp-btn');
const clearLogsBtn = document.getElementById('clear-logs-btn');

let eventSource = null;
let statusPollInterval = null;

export function initJobs() {
    runSyncBtn.addEventListener('click', async () => {
        try {
            await API.triggerDownload(true);
            updateJobsStatus();
        } catch (e) {
            alert(`Failed to trigger download: ${e.message}`);
        }
    });

    runRssBtn.addEventListener('click', async () => {
        try {
            await API.triggerRss();
            updateJobsStatus();
        } catch (e) {
            alert(`Failed to trigger RSS: ${e.message}`);
        }
    });

    updateYtdlpBtn.addEventListener('click', async () => {
        if (confirm('This will update yt-dlp and restart the backend. Connection will drop momentarily. Proceed?')) {
            try {
                await API.triggerUpdateYtdlp();
                updateJobsStatus();
            } catch (e) {
                alert(`Failed to trigger update: ${e.message}`);
            }
        }
    });

    clearLogsBtn.addEventListener('click', () => {
        logConsole.textContent = '';
    });

    // Start logs stream
    startLogsStream();

    // Start status polling
    if (statusPollInterval) clearInterval(statusPollInterval);
    statusPollInterval = setInterval(updateJobsStatus, 3000);
    updateJobsStatus();
}

function startLogsStream() {
    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource('/api/jobs/logs/stream');

    logStatusDot.textContent = 'Connecting...';
    logStatusDot.className = 'badge';

    eventSource.onopen = () => {
        logStatusDot.textContent = 'Live';
        logStatusDot.className = 'badge badge-success';
    };

    eventSource.onerror = () => {
        logStatusDot.textContent = 'Offline (Retrying)';
        logStatusDot.className = 'badge badge-accent';
    };

    eventSource.onmessage = (event) => {
        const line = event.data;
        appendLogLine(line);
    };
}

function appendLogLine(line) {
    const span = document.createElement('span');
    span.textContent = line + '\n';

    if (line.includes(' - ERROR - ') || line.includes(' - CRITICAL - ') || line.includes('Error') || line.includes('ERROR') || line.includes('failed')) {
        span.className = 'error';
    } else if (line.includes(' - WARNING - ') || line.includes('warning') || line.includes('WARNING')) {
        span.className = 'warning';
    } else if (line.includes('complete') || line.includes('Success') || line.includes('updated successfully') || line.includes('sync complete') || line.includes('Finished')) {
        span.className = 'success';
    } else {
        span.className = 'info';
    }

    logConsole.appendChild(span);
    
    // Limit log display lines to prevent browser slowdown (keep last 500 lines)
    if (logConsole.childNodes.length > 500) {
        logConsole.removeChild(logConsole.firstChild);
    }
    
    logConsole.scrollTop = logConsole.scrollHeight;
}

export async function updateJobsStatus() {
    try {
        const status = await API.getJobsStatus();
        
        systemStateLabel.textContent = status.running ? 'Running' : 'Idle';
        systemStateLabel.className = status.running ? 'badge badge-accent' : 'badge';
        
        if (status.running) {
            lastJobName.textContent = status.current_job;
            lastJobCode.textContent = 'Running';
            lastJobCode.style.color = 'var(--accent-color)';
        } else {
            lastJobName.textContent = status.current_job || 'None';
            lastJobCode.textContent = status.last_exit_code === 0 ? 'Success' : `Failed (${status.last_exit_code})`;
            lastJobCode.style.color = status.last_exit_code === 0 ? 'var(--success-color)' : 'var(--danger-color)';
        }
    } catch (e) {
        console.error('Failed to fetch jobs status', e);
    }
}
