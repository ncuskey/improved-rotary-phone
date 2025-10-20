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
        document.getElementById('book-search')?.focus();
    }

    // Ctrl/Cmd + I: Focus ISBN input
    if ((event.ctrlKey || event.metaKey) && event.key === 'i') {
        event.preventDefault();
        document.getElementById('entry-isbn')?.focus();
    }
});

// Initialize status on load
document.addEventListener('DOMContentLoaded', () => {
    setStatus('Ready');
});
function bookEntry() {
    return {
        isbnInput: '',
        pendingIsbn: '',
        lastScanned: '',
        metadata: null,
        evaluation: null,
        isSubmitting: false,
        isEvaluating: false,
        isRefreshingMetadata: false,
        isDeleting: false,
        errorMessage: '',
        successMessage: '',
        attributes: {
            condition: 'Good',
            coverType: 'Unknown',
            firstEdition: false,
            printing: '',
            signed: false,
        },
        conditions: ['New', 'Like New', 'Very Good', 'Good', 'Acceptable', 'Poor'],
        coverTypes: ['Hardcover', 'Paperback', 'Trade Paperback', 'Mass Market', 'Unknown'],
        printings: ['First Printing', 'Second Printing', 'Later Printing', 'Book Club Edition'],
        init() {
            this.focusInput();
            // Watch for attribute changes to re-evaluate
            this.$watch('attributes.condition', () => this.onAttributeChange());
            this.$watch('attributes.firstEdition', () => this.onAttributeChange());
            this.$watch('attributes.printing', () => this.onAttributeChange());
            this.$watch('attributes.signed', () => this.onAttributeChange());
        },
        onAttributeChange() {
            // Re-evaluate if we have a pending ISBN and metadata
            if (this.pendingIsbn && this.metadata && !this.isEvaluating) {
                this.reEvaluate();
            }
        },
        async reEvaluate() {
            if (!this.pendingIsbn || this.isEvaluating) return;

            this.isEvaluating = true;
            try {
                // Build edition notes from attributes
                const editionNotes = this.computeEditionNotes();

                // Fetch updated evaluation with new condition/edition
                const params = new URLSearchParams({
                    condition: this.attributes.condition,
                });
                if (editionNotes) {
                    params.append('edition', editionNotes);
                }

                console.log('Re-evaluating with:', {
                    isbn: this.pendingIsbn,
                    condition: this.attributes.condition,
                    edition: editionNotes,
                    url: `/api/books/${encodeURIComponent(this.pendingIsbn)}/evaluate?${params}`
                });

                const evalResp = await fetch(`/api/books/${encodeURIComponent(this.pendingIsbn)}/evaluate?${params}`);
                if (!evalResp.ok) {
                    throw new Error('Failed to fetch updated evaluation');
                }

                const data = await evalResp.json();
                console.log('Updated evaluation:', data);
                this.evaluation = data;
            } catch (error) {
                console.error('Re-evaluation error', error);
            } finally {
                this.isEvaluating = false;
            }
        },
        focusInput() {
            this.$nextTick(() => {
                if (this.$refs && this.$refs.isbnInput) {
                    this.$refs.isbnInput.focus();
                    if (typeof this.$refs.isbnInput.select === 'function') {
                        this.$refs.isbnInput.select();
                    }
                }
            });
        },
        resetMessages() {
            this.errorMessage = '';
            this.successMessage = '';
        },
        attributeSummary() {
            const parts = [];
            if (this.attributes.firstEdition) parts.push('First Edition');
            if (this.attributes.printing) parts.push(this.attributes.printing);
            if (this.attributes.signed) parts.push('Signed');
            if (this.attributes.coverType && this.attributes.coverType !== 'Unknown') {
                parts.push(this.attributes.coverType);
            }
            return parts.join(' · ');
        },
        resetAttributes() {
            this.attributes = {
                condition: 'Good',
                coverType: 'Unknown',
                firstEdition: false,
                printing: '',
                signed: false,
            };
        },
        computeEditionNotes() {
            const parts = [];
            if (this.attributes.firstEdition) parts.push('First Edition');
            if (this.attributes.printing) parts.push(this.attributes.printing);
            if (this.attributes.signed) parts.push('Signed');
            return parts.join(', ');
        },
        buildPayload(isbn) {
            const payload = {
                isbn,
                condition: this.attributes.condition,
            };
            const editionNotes = this.computeEditionNotes();
            if (editionNotes) {
                payload.edition = editionNotes;
            }
            if (this.attributes.coverType && this.attributes.coverType !== 'Unknown') {
                payload.cover_type = this.attributes.coverType;
            }
            if (this.attributes.printing) {
                payload.printing = this.attributes.printing;
            }
            payload.signed = this.attributes.signed;
            return payload;
        },
        normalizeIsbn(value) {
            const digits = value.replace(/[^0-9Xx]/g, '');
            return digits || value.trim();
        },
        async submitScan() {
            if (this.isSubmitting) return;
            const raw = this.isbnInput.trim();
            if (!raw) return;

            this.resetMessages();
            this.isSubmitting = true;
            this.isEvaluating = false;
            this.metadata = null;
            this.evaluation = null;

            const normalized = this.normalizeIsbn(raw);
            this.pendingIsbn = normalized;

            try {
                const payload = this.buildPayload(normalized);
                const resp = await fetch('/isbn', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload),
                });

                if (!resp.ok) {
                    const text = await resp.text();
                    throw new Error(text || `Scan failed (${resp.status})`);
                }

                const data = await resp.json();
                const resolvedIsbn = data.isbn || normalized;
                this.pendingIsbn = resolvedIsbn;
                this.lastScanned = resolvedIsbn;

                this.metadata = {
                    isbn: resolvedIsbn,
                    title: data.title || 'Untitled',
                    subtitle: data.subtitle || '',
                    author: data.author || '',
                    authors: data.authors || (data.author ? [data.author] : []),
                    thumbnail: data.thumbnail || (resolvedIsbn ? `https://covers.openlibrary.org/b/isbn/${resolvedIsbn}-M.jpg` : ''),
                    description: data.description || '',
                    categories: data.categories || [],
                    published_year: data.published_year || null,
                };

                this.successMessage = `Added ${this.metadata.title || resolvedIsbn}`;
                showToast(this.successMessage, 'success');

                this.refreshTable(resolvedIsbn);
                this.loadDetail(resolvedIsbn);
                this.fetchEvaluation(resolvedIsbn);
            } catch (error) {
                console.error('Scan error', error);
                this.errorMessage = error.message || 'Failed to scan ISBN.';
                showToast(this.errorMessage, 'error');
                this.isEvaluating = false;
            } finally {
                this.isSubmitting = false;
                this.focusInput();
            }
        },
        async fetchEvaluation(isbn, attempt = 0) {
            this.isEvaluating = true;
            try {
                const resp = await fetch(`/api/books/${encodeURIComponent(isbn)}/evaluate`);
                if (resp.status === 404) {
                    if (attempt < 4) {
                        const delay = 700 * (attempt + 1);
                        setTimeout(() => this.fetchEvaluation(isbn, attempt + 1), delay);
                        return;
                    }
                    throw new Error('Evaluation not ready yet.');
                }

                if (!resp.ok) {
                    const text = await resp.text();
                    throw new Error(text || `Evaluation failed (${resp.status})`);
                }

                const data = await resp.json();
                this.evaluation = data;
                this.successMessage = 'Analysis ready. Accept or reject to continue.';
                showToast('Analysis complete', 'info');
                this.isEvaluating = false;
            } catch (error) {
                console.error('Evaluation error', error);
                this.errorMessage = error.message || 'Failed to fetch evaluation.';
                showToast(this.errorMessage, 'warning');
                this.isEvaluating = false;
            }
        },
        refreshTable(isbn) {
            const hidden = document.getElementById('selected-isbn');
            if (hidden) {
                hidden.value = isbn || '';
            }
            window.dispatchEvent(new Event('refresh-books'));
        },
        loadDetail(isbn) {
            if (window.htmx) {
                htmx.ajax('GET', `/api/books/${encodeURIComponent(isbn)}`, { target: '#book-detail', swap: 'innerHTML' });
            }
        },
        resetForm(resetAttributes = true) {
            this.resetMessages();
            this.isbnInput = '';
            this.pendingIsbn = '';
            this.metadata = null;
            this.evaluation = null;
            this.isEvaluating = false;
            this.isDeleting = false;
            if (resetAttributes) {
                this.resetAttributes();
            }
            this.focusInput();
        },
        async acceptBook() {
            if (!this.pendingIsbn) return;

            // Save current attributes to database before accepting
            try {
                const editionNotes = this.computeEditionNotes();
                await fetch(`/api/books/${encodeURIComponent(this.pendingIsbn)}`, {
                    method: 'PATCH',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: new URLSearchParams({
                        condition: this.attributes.condition,
                        edition: editionNotes || '',
                    }),
                });
            } catch (error) {
                console.error('Failed to save book attributes:', error);
            }

            this.lastScanned = this.pendingIsbn;
            this.successMessage = 'Ready for next scan.';
            showToast('Ready for next scan', 'success');
            this.resetForm(false);
        },
        async rejectBook() {
            if (!this.pendingIsbn || this.isDeleting) return;
            this.resetMessages();
            this.isDeleting = true;
            try {
                const resp = await fetch(`/api/books/${encodeURIComponent(this.pendingIsbn)}/json`, {
                    method: 'DELETE',
                });
                if (!resp.ok) {
                    const text = await resp.text();
                    throw new Error(text || `Failed to delete (${resp.status})`);
                }
                showToast('Book removed', 'info');
                this.refreshTable('');
                this.resetForm();
            } catch (error) {
                console.error('Reject error', error);
                this.errorMessage = error.message || 'Failed to remove book.';
                showToast(this.errorMessage, 'error');
                this.isDeleting = false;
            }
        },
        openImportModal() {
            const modal = document.getElementById('import-modal');
            if (modal) {
                modal.classList.remove('hidden');
            }
        },
        async refreshMetadata() {
            if (this.isRefreshingMetadata) return;
            this.isRefreshingMetadata = true;
            try {
                const resp = await fetch('/api/actions/refresh-metadata', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ limit: 100 }),
                });
                if (!resp.ok) {
                    const text = await resp.text();
                    throw new Error(text || `Refresh failed (${resp.status})`);
                }
                showToast('Metadata refresh started', 'success');
            } catch (error) {
                console.error('Refresh metadata error', error);
                showToast(error.message || 'Failed to refresh metadata', 'error');
            } finally {
                this.isRefreshingMetadata = false;
            }
        },
        formatUSD(value) {
            if (value === null || value === undefined || value === '') return '—';
            const number = Number(value);
            if (Number.isNaN(number)) return '—';
            return new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: 'USD',
                maximumFractionDigits: 2,
            }).format(number);
        },
        formatPercent(value) {
            if (value === null || value === undefined) return '—';
            const number = Number(value);
            if (Number.isNaN(number)) return '—';
            return `${Math.round(number * 100)}%`;
        },
        formatProbability(value) {
            if (value === null || value === undefined) return '';
            const number = Number(value);
            if (Number.isNaN(number)) return '';
            // probability_score is already on 0-100 scale, don't multiply
            return `${Math.round(number)}%`;
        },
        formatRank(rank) {
            if (rank === null || rank === undefined) return '—';
            const number = Number(rank);
            if (Number.isNaN(number)) return '—';
            if (number < 1000) return `#${number}`;
            if (number < 100000) return `#${Math.round(number / 1000)}k`;
            return `#${Math.round(number / 1000)}k`;
        },
        formatDate(iso) {
            if (!iso) return '';
            const date = new Date(iso);
            if (Number.isNaN(date.getTime())) return iso;
            return date.toLocaleDateString();
        },
        bestBuybackLabel(evaluation) {
            if (evaluation && evaluation.bookscouter && evaluation.bookscouter.best_price) {
                return this.formatUSD(evaluation.bookscouter.best_price);
            }
            if (evaluation && evaluation.booksrun && evaluation.booksrun.cash_price) {
                return this.formatUSD(evaluation.booksrun.cash_price);
            }
            return '—';
        },
        marketAvgLabel(value) {
            if (value === null || value === undefined) return '—';
            return `Avg ${this.formatUSD(value)}`;
        },
        probabilityBadgeClasses(label) {
            if (!label) return 'bg-gray-100 text-gray-600';
            const lower = label.toLowerCase();
            if (lower.includes('strong') || lower.includes('excellent')) {
                return 'bg-green-100 text-green-700';
            }
            if (lower.includes('worth') || lower.includes('good')) {
                return 'bg-blue-100 text-blue-700';
            }
            if (lower.includes('risky')) {
                return 'bg-yellow-100 text-yellow-700';
            }
            return 'bg-red-100 text-red-700';
        },
    };
}
window.bookEntry = bookEntry;
