import { API } from './api.js';

const channelsGrid = document.getElementById('channels-grid');
const addChannelBtn = document.getElementById('add-channel-btn');
const addChannelModal = document.getElementById('add-channel-modal');
const addChannelForm = document.getElementById('add-channel-form');

const editChannelModal = document.getElementById('edit-channel-modal');
const editChannelForm = document.getElementById('edit-channel-form');

export function initChannels() {
    addChannelBtn.addEventListener('click', () => {
        addChannelForm.reset();
        addChannelModal.classList.add('active');
    });
    
    addChannelForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const id = document.getElementById('add-chan-id').value.trim();
        const url = document.getElementById('add-chan-url').value.trim();
        const limit = parseInt(document.getElementById('add-chan-limit').value);
        const sponsorblock = document.getElementById('add-chan-sponsorblock').checked;
        const interval = parseInt(document.getElementById('add-chan-interval').value);
        
        try {
            await API.createChannel(id, url, limit, sponsorblock, interval);
            addChannelModal.classList.remove('active');
            loadChannelsList();
        } catch (err) {
            alert(`Error adding channel: ${err.message}`);
        }
    });
    
    editChannelForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const id = document.getElementById('edit-chan-id').value;
        const limit = parseInt(document.getElementById('edit-chan-limit').value);
        const sponsorblock = document.getElementById('edit-chan-sponsorblock').checked;
        const interval = parseInt(document.getElementById('edit-chan-interval').value);
        
        try {
            await API.updateChannel(id, limit, sponsorblock, interval);
            editChannelModal.classList.remove('active');
            loadChannelsList();
        } catch (err) {
            alert(`Error updating channel: ${err.message}`);
        }
    });
}

export async function loadChannelsList() {
    channelsGrid.innerHTML = '<div style="color: var(--text-secondary);">Loading subscribed feeds...</div>';
    try {
        const channels = await API.getChannels();
        if (channels.length === 0) {
            channelsGrid.innerHTML = `
                <div style="grid-column: 1 / -1; text-align: center; padding: 3rem; color: var(--text-secondary);">
                    <p style="font-size: 1.25rem; margin-bottom: 1.25rem;">No feeds subscribed yet.</p>
                    <button id="channels-empty-btn" class="btn btn-primary">➕ Subscribe Now</button>
                </div>
            `;
            document.getElementById('channels-empty-btn').addEventListener('click', () => {
                addChannelBtn.click();
            });
            return;
        }
        
        channelsGrid.innerHTML = channels.map(c => {
            const lastCheckText = c.last_check 
                ? new Date(c.last_check * 1000).toLocaleString() 
                : 'Never';
            const nextCheckText = c.next_check 
                ? new Date(c.next_check * 1000).toLocaleString() 
                : 'Pending';
                
            return `
                <div class="card">
                    <div class="card-header" style="margin-bottom: 1rem;">
                        <h3 class="card-title">📺 ${c.id}</h3>
                        <span class="badge ${c.audio_count > 0 ? 'badge-success' : ''}">${c.audio_count} eps</span>
                    </div>
                    <div class="card-meta">
                        <span style="word-break: break-all;"><strong>Source URL:</strong> <a href="${c.url}" target="_blank">${c.url}</a></span>
                        <span><strong>Keep Limit:</strong> Newer ${c.limit}</span>
                        <span><strong>SponsorBlock:</strong> ${c.sponsorblock ? 'Remove Sponsors' : 'Disabled'}</span>
                        <span><strong>Interval:</strong> Every ${c.check_interval_hours} hr(s)</span>
                        <span><strong>Last Checked:</strong> ${lastCheckText}</span>
                        <span><strong>Next Check:</strong> ${nextCheckText}</span>
                    </div>
                    <div class="card-actions">
                        <button class="btn btn-sm btn-edit" data-id="${c.id}" data-url="${c.url}" data-limit="${c.limit}" data-sponsorblock="${c.sponsorblock}" data-interval="${c.check_interval_hours}">Edit</button>
                        <button class="btn btn-sm btn-danger btn-delete" data-id="${c.id}">Delete</button>
                    </div>
                </div>
            `;
        }).join('');
        
        // Setup action listeners
        document.querySelectorAll('.btn-edit').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = btn.dataset.id;
                document.getElementById('edit-chan-id').value = id;
                document.getElementById('edit-chan-url').value = btn.dataset.url;
                document.getElementById('edit-chan-limit').value = btn.dataset.limit;
                document.getElementById('edit-chan-sponsorblock').checked = btn.dataset.sponsorblock === 'true';
                document.getElementById('edit-chan-interval').value = btn.dataset.interval;
                
                document.getElementById('edit-modal-title').textContent = `Edit Feed: ${id}`;
                editChannelModal.classList.add('active');
            });
        });
        
        document.querySelectorAll('.btn-delete').forEach(btn => {
            btn.addEventListener('click', async () => {
                const id = btn.dataset.id;
                if (confirm(`Are you sure you want to delete ${id}? This will permanently remove all downloaded episodes, RSS feeds, and check history.`)) {
                    try {
                        await API.deleteChannel(id);
                        loadChannelsList();
                    } catch (err) {
                        alert(`Error deleting channel: ${err.message}`);
                    }
                }
            });
        });
        
    } catch (err) {
        channelsGrid.innerHTML = `<div style="color: var(--danger-color); grid-column: 1/-1;">Error: ${err.message}</div>`;
    }
}
