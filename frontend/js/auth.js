// frontend/js/auth.js

class Auth {
    static isAuthenticated() {
        return !!localStorage.getItem('auth_token');
    }

    static login(token) {
        localStorage.setItem('auth_token', token);
    }

    static logout() {
        localStorage.removeItem('auth_token');
        window.location.href = 'index.html';
    }

    static requireAuth() {
        if (!this.isAuthenticated()) {
            window.location.href = 'index.html';
        }
    }

    static redirectIfAuthenticated() {
        if (this.isAuthenticated()) {
            window.location.href = 'dashboard.html';
        }
    }
}
