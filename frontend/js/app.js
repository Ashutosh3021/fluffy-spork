// frontend/js/app.js

class App {
    static showAlert(id, message, type = 'error') {
        const alertEl = document.getElementById(id);
        if (alertEl) {
            alertEl.textContent = message;
            alertEl.className = `alert alert-${type} show`;

            // Auto hide after 5 seconds
            setTimeout(() => {
                alertEl.classList.remove('show');
            }, 5000);
        }
    }

    static hideAlert(id) {
        const alertEl = document.getElementById(id);
        if (alertEl) {
            alertEl.classList.remove('show');
        }
    }

    static setLoading(btnId, isLoading, originalText = 'Submit') {
        const btn = document.getElementById(btnId);
        if (btn) {
            btn.disabled = isLoading;
            if (isLoading) {
                btn.innerHTML = `<span class="spinner"></span> Loading...`;
            } else {
                btn.textContent = originalText;
            }
        }
    }

    static formatDate(isoString) {
        if (!isoString) return 'Never';
        const date = new Date(isoString);
        return date.toLocaleString();
    }

    static setupNavigation() {
        const logoutBtn = document.getElementById('logout-btn');
        if (logoutBtn) {
            logoutBtn.addEventListener('click', (e) => {
                e.preventDefault();
                Auth.logout();
            });
        }
    }
}

// Initialize shared components when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    App.setupNavigation();
});

    static escapeHtml(unsafe) {
        if (!unsafe) return '';
        return String(unsafe)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }
