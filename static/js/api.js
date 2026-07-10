// API fetch wrapper for PodQueue

async function request(url, options = {}) {
    const defaultHeaders = {
        'Content-Type': 'application/json',
    };
    
    options.headers = {
        ...defaultHeaders,
        ...options.headers,
    };
    
    try {
        const response = await fetch(url, options);
        if (response.status === 401) {
            window.dispatchEvent(new CustomEvent('auth-unauthorized'));
            throw new Error('Unauthorized');
        }
        
        if (!response.ok) {
            const errData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errData.detail || `Request failed: ${response.status}`);
        }
        
        if (response.status === 204) return null;
        return await response.json();
    } catch (error) {
        console.error(`API Error on ${url}:`, error);
        throw error;
    }
}

export const API = {
    async checkAuth() {
        return await request('/api/me');
    },
    
    async login(password) {
        return await request('/api/login', {
            method: 'POST',
            body: JSON.stringify({ password }),
        });
    },
    
    async logout() {
        return await request('/api/logout', {
            method: 'POST',
        });
    },
    
    async getChannels() {
        return await request('/api/channels');
    },
    
    async createChannel(id, url, limit, sponsorblock, check_interval_hours) {
        return await request('/api/channels', {
            method: 'POST',
            body: JSON.stringify({ id, url, limit, sponsorblock, check_interval_hours }),
        });
    },
    
    async updateChannel(id, limit, sponsorblock, check_interval_hours) {
        return await request(`/api/channels/${id}`, {
            method: 'PUT',
            body: JSON.stringify({ limit, sponsorblock, check_interval_hours }),
        });
    },
    
    async deleteChannel(id) {
        return await request(`/api/channels/${id}`, {
            method: 'DELETE',
        });
    },
    
    async getJobsStatus() {
        return await request('/api/jobs/status');
    },
    
    async triggerDownload(force = false) {
        return await request('/api/jobs/download', {
            method: 'POST',
            body: JSON.stringify({ force }),
        });
    },
    
    async triggerRss() {
        return await request('/api/jobs/rss', {
            method: 'POST',
        });
    },
    
    async triggerUpdateYtdlp() {
        return await request('/api/jobs/update-ytdlp', {
            method: 'POST',
        });
    },
    
    async getFeeds() {
        return await request('/api/feeds');
    }
};
export default API;
