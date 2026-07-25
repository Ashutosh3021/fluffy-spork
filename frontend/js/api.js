// frontend/js/api.js
const API_BASE_URL = 'https://fluffy-spork-iy00.onrender.com/api';

class ApiClient {
    static async request(endpoint, options = {}) {
        const token = localStorage.getItem('auth_token');
        const headers = {
            'Content-Type': 'application/json',
            ...(options.headers || {})
        };

        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const config = {
            ...options,
            headers
        };

        if (options.body && typeof options.body === 'object') {
            config.body = JSON.stringify(options.body);
        }

        try {
            const response = await fetch(`${API_BASE_URL}${endpoint}`, config);
            const data = await response.json();

            if (!response.ok) {
                if (response.status === 401) {
                    // Unauthorized, clear token and redirect to login
                    localStorage.removeItem('auth_token');
                    if (!window.location.pathname.endsWith('index.html') && window.location.pathname !== '/' && window.location.pathname !== '/frontend/' && window.location.pathname !== '/frontend/index.html') {
                        window.location.href = 'index.html';
                    }
                }
                throw new Error(data.error || 'API request failed');
            }

            return data;
        } catch (error) {
            console.error('API Error:', error);
            throw error;
        }
    }

    static get(endpoint) {
        return this.request(endpoint, { method: 'GET' });
    }

    static post(endpoint, body) {
        return this.request(endpoint, { method: 'POST', body });
    }

    static put(endpoint, body) {
        return this.request(endpoint, { method: 'PUT', body });
    }

    static delete(endpoint) {
        return this.request(endpoint, { method: 'DELETE' });
    }
}
