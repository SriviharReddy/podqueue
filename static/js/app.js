import { API } from './api.js';
import { initChannels, loadChannelsList } from './channels.js';
import { initJobs, updateJobsStatus } from './jobs.js';

const loginScreen = document.getElementById('login-screen');
const appLayout = document.getElementById('app-layout');
const loginForm = document.getElementById('login-form');
const loginPassword = document.getElementById('admin-password');
const loginError = document.getElementById('login-error');
const logoutBtn = document.getElementById('logout-btn');

const navItems = document.querySelectorAll('.nav-item');
const views = document.querySelectorAll('.view-section');

export function switchView(targetId) {
    views.forEach(view => {
        if (view.id === targetId) {
            view.classList.add('active');
        } else {
            view.classList.remove('active');
        }
    });
    
    navItems.forEach(item => {
        if (item.dataset.target === targetId) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
    
    if (targetId === 'channels-view') {
        loadChannelsList();
    } else if (targetId === 'jobs-view') {
        updateJobsStatus();
    } else if (targetId === 'settings-view') {
        loadFeedsList();
    }
}

async function loadFeedsList() {
    const feedsList = document.getElementById('feeds-list');
    feedsList.innerHTML = '<div style="color: var(--text-secondary);">Loading feeds...</div>';
    try {
        const feeds = await API.getFeeds();
        if (feeds.length === 0) {
            feedsList.innerHTML = '<div style="color: var(--text-secondary); grid-column: 1/-1;">No generated podcast feeds found. Run a sync job first.</div>';
            return;
        }
        feedsList.innerHTML = feeds.map(feed => `
            <div class="card">
                <div class="card-header" style="margin-bottom: 0.5rem;">
                    <h3 class="card-title">📻 ${feed.title}</h3>
                </div>
                <div class="card-meta">
                    <span style="word-break: break-all;"><strong>Feed URL:</strong> <a href="${feed.url}" target="_blank">${feed.url}</a></span>
                    <span style="margin-top: 0.5rem;"><strong>Downloaded Episodes:</strong> ${feed.audio_count}</span>
                </div>
                <button class="btn btn-sm btn-primary copy-feed-btn" data-url="${feed.url}">Copy URL</button>
            </div>
        `).join('');

        // Register copy button listeners
        document.querySelectorAll('.copy-feed-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const url = btn.dataset.url;
                navigator.clipboard.writeText(url).then(() => {
                    const originalText = btn.textContent;
                    btn.textContent = 'Copied!';
                    setTimeout(() => btn.textContent = originalText, 1500);
                });
            });
        });
    } catch (err) {
        feedsList.innerHTML = `<div style="color: var(--danger-color); grid-column: 1/-1;">Failed to load feeds: ${err.message}</div>`;
    }
}

async function init() {
    window.addEventListener('auth-unauthorized', showLogin);
    
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            switchView(item.dataset.target);
        });
    });
    
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        loginError.style.display = 'none';
        try {
            await API.login(loginPassword.value);
            showApp();
        } catch (err) {
            loginError.textContent = 'Incorrect password. Please try again.';
            loginError.style.display = 'block';
        }
    });
    
    logoutBtn.addEventListener('click', async () => {
        try {
            await API.logout();
        } catch (e) {}
        showLogin();
    });
    
    try {
        await API.checkAuth();
        showApp();
    } catch (err) {
        showLogin();
    }
}

function showLogin() {
    appLayout.style.display = 'none';
    loginScreen.style.display = 'flex';
    loginPassword.value = '';
}

function showApp() {
    loginScreen.style.display = 'none';
    appLayout.style.display = 'flex';
    
    initChannels();
    initJobs();
    
    switchView('channels-view');
}

// Global Close Modal click listeners
document.querySelectorAll('[data-close]').forEach(btn => {
    btn.addEventListener('click', () => {
        const modalId = btn.dataset.close;
        document.getElementById(modalId).classList.remove('active');
    });
});

document.addEventListener('DOMContentLoaded', init);
