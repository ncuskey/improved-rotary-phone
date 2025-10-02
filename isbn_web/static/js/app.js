// ISBN Lot Optimizer - Client-side JavaScript

// Toast notification system
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');

    const colors = {
        success: 'bg-green-500',
        error: 'bg-red-500',
        warning: 'bg-yellow-500',
        info: 'bg-blue-500'
    };

    toast.className = `${colors[type]} text-white px-6 py-3 rounded-lg shadow-lg transform transition-all duration-300 translate-x-0`;
    toast.textContent = message;

    container.appendChild(toast);

    // Auto-remove after 3 seconds
    setTimeout(() => {
        toast.classList.add('translate-x-full', 'opacity-0');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Status bar helper
function setStatus(message) {
    const statusEl = document.getElementById('status-message');
    if (statusEl) {
        statusEl.textContent = message;
    }
}

// Progress bar helper
function showProgress(percent, label = '') {
    const progressBar = document.getElementById('progress-bar');
    const progressFill = document.getElementById('progress-bar-fill');
    const progressText = document.getElementById('progress-text');

    if (progressBar && progressFill && progressText) {
        progressBar.classList.remove('hidden');
        progressFill.style.width = `${percent}%`;
        progressText.textContent = label || `${percent}%`;
    }
}

function hideProgress() {
    const progressBar = document.getElementById('progress-bar');
    if (progressBar) {
        progressBar.classList.add('hidden');
    }
}

// Update book count after table loads
function updateBookCount() {
    const bookTable = document.getElementById('book-table');
    if (bookTable) {
        const rows = bookTable.querySelectorAll('tbody tr');
        const count = rows.length;
        const countEl = document.getElementById('book-count');
        if (countEl) {
            countEl.textContent = `Showing ${count} book${count !== 1 ? 's' : ''}`;
        }
    }
}

// HTMX event handlers
document.addEventListener('htmx:afterRequest', (event) => {
    if (event.detail.successful) {
        // Check if there's a success message in response headers
        const message = event.detail.xhr.getResponseHeader('X-Success-Message');
        if (message) {
            showToast(message, 'success');
        }

        // Update book count if book table was loaded
        if (event.detail.target && event.detail.target.id === 'book-table') {
            updateBookCount();
        }
    } else {
        showToast('Request failed. Please try again.', 'error');
    }
});

// Global keyboard shortcuts
document.addEventListener('keydown', (event) => {
    // Ctrl/Cmd + K: Focus search
    if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
        event.preventDefault();
        document.getElementById('search')?.focus();
    }

    // Ctrl/Cmd + I: Focus ISBN input
    if ((event.ctrlKey || event.metaKey) && event.key === 'i') {
        event.preventDefault();
        document.getElementById('isbn')?.focus();
    }
});

// Initialize status on load
document.addEventListener('DOMContentLoaded', () => {
    setStatus('Ready');
});
