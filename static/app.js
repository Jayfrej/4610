// MT5 Trading Bot Frontend JavaScript
class TradingBotUI {
    constructor() {
        this.accounts = [];
        this.webhookUrl = '';
        this.currentAction = null;
        this.refreshInterval = null;
        
        this.init();
    }
    
    init() {
        this.setupEventListeners();
        this.loadData();
        this.startAutoRefresh();
        this.updateLastUpdateTime();
        
        console.log('Trading Bot UI initialized');
    }
    
    setupEventListeners() {
        // Form submission
        document.getElementById('addAccountForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.addAccount();
        });
        
        // Refresh button
        document.getElementById('refreshBtn').addEventListener('click', () => {
            this.loadData();
        });
        
        // Webhook copy button
        document.getElementById('webhookBtn').addEventListener('click', () => {
            this.copyWebhookUrl();
        });
        
        // Search functionality
        document.getElementById('searchInput').addEventListener('input', (e) => {
            this.filterTable(e.target.value);
        });
        
        // Modal close events
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal-overlay')) {
                this.closeModal();
            }
        });
        
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                this.closeModal();
            }
        });
        
        // Auto-refresh on visibility change
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                this.loadData();
            }
        });
    }
    
    async loadData() {
        try {
            this.showLoading();
            
            // Load accounts and webhook URL in parallel
            const [accountsResponse, webhookResponse] = await Promise.all([
                fetch('/accounts'),
                fetch('/webhook-url')
            ]);
            
            if (accountsResponse.ok) {
                const accountsData = await accountsResponse.json();
                this.accounts = accountsData.accounts;
                this.updateAccountsTable();
                this.updateStats();
            }
            
            if (webhookResponse.ok) {
                const webhookData = await webhookResponse.json();
                this.webhookUrl = webhookData.url;
                this.updateWebhookDisplay();
            }
            
            this.updateLastUpdateTime();
            this.showToast('Data refreshed successfully', 'success');
            
        } catch (error) {
            console.error('Failed to load data:', error);
            this.showToast('Failed to load data', 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    async addAccount() {
        const formData = new FormData(document.getElementById('addAccountForm'));
        const account = formData.get('account').trim();
        const nickname = formData.get('nickname').trim();
        
        if (!account) {
            this.showToast('Please enter account number', 'warning');
            return;
        }
        
        try {
            this.showLoading();
            
            const response = await fetch('/accounts', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ account, nickname })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                this.showToast('Account added successfully', 'success');
                document.getElementById('addAccountForm').reset();
                this.loadData();
            } else {
                this.showToast(data.error || 'Failed to add account', 'error');
            }
            
        } catch (error) {
            console.error('Failed to add account:', error);
            this.showToast('Failed to add account', 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    async performAccountAction(account, action, confirmMessage) {
        if (confirmMessage && !await this.showConfirmDialog('Confirm Action', confirmMessage)) {
            return;
        }
        
        try {
            this.showLoading();
            
            let endpoint = `/accounts/${account}/${action}`;
            let method = 'POST';
            
            if (action === 'delete') {
                endpoint = `/accounts/${account}`;
                method = 'DELETE';
            }
            
            const response = await fetch(endpoint, { method });
            const data = await response.json();
            
            if (response.ok) {
                this.showToast(`Account ${action} successful`, 'success');
                this.loadData();
            } else {
                this.showToast(data.error || `Failed to ${action} account`, 'error');
            }
            
        } catch (error) {
            console.error(`Failed to ${action} account:`, error);
            this.showToast(`Failed to ${action} account`, 'error');
        } finally {
            this.hideLoading();
        }
    }
    
    updateAccountsTable() {
        const tbody = document.getElementById('accountsTableBody');
        
        if (this.accounts.length === 0) {
            tbody.innerHTML = `
                <tr class="no-data">
                    <td colspan="6">
                        <div class="no-data-message">
                            <i class="fas fa-inbox"></i>
                            <p>No accounts found. Add your first account above.</p>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }
        
        tbody.innerHTML = this.accounts.map(account => {
            const createdDate = new Date(account.created).toLocaleString();
            const statusClass = account.status.toLowerCase();
            const statusIcon = account.status === 'Online' ? 'circle' : 'circle';
            
            return `
                <tr data-account="${account.account}">
                    <td>
                        <span class="status-badge ${statusClass}">
                            <i class="fas fa-${statusIcon}"></i>
                            ${account.status}
                        </span>
                    </td>
                    <td>
                        <strong>${account.account}</strong>
                    </td>
                    <td>${account.nickname || '-'}</td>
                    <td>${account.pid || '-'}</td>
                    <td title="${createdDate}">${this.formatDate(account.created)}</td>
                    <td>
                        <div class="action-buttons">
                            ${account.status === 'Online' ? `
                                <button class="btn btn-warning btn-sm" onclick="ui.performAccountAction('${account.account}', 'restart', 'Are you sure you want to restart this account?')" title="Restart">
                                    <i class="fas fa-redo"></i>
                                </button>
                                <button class="btn btn-danger btn-sm" onclick="ui.performAccountAction('${account.account}', 'stop', 'Are you sure you want to stop this account?')" title="Stop">
                                    <i class="fas fa-stop"></i>
                                </button>
                            ` : `
                                <button class="btn btn-success btn-sm" onclick="ui.performAccountAction('${account.account}', 'open')" title="Open">
                                    <i class="fas fa-play"></i>
                                </button>
                            `}
                            <button class="btn btn-secondary btn-sm" onclick="ui.performAccountAction('${account.account}', 'delete', 'Are you sure you want to delete this account? This action cannot be undone.')" title="Delete">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join('');
    }
    
    updateStats() {
        const total = this.accounts.length;
        const online = this.accounts.filter(acc => acc.status === 'Online').length;
        const offline = total - online;
        
        document.getElementById('totalAccounts').textContent = total;
        document.getElementById('onlineAccounts').textContent = online;
        document.getElementById('offlineAccounts').textContent = offline;
        
        // Update server status
        document.getElementById('serverStatus').textContent = 'Online';
        document.getElementById('serverStatus').className = 'status-badge online';
    }
    
    updateWebhookDisplay() {
        const webhookElement = document.getElementById('webhookEndpoint');
        if (webhookElement && this.webhookUrl) {
            webhookElement.textContent = this.webhookUrl;
        }
    }
    
    updateLastUpdateTime() {
        const now = new Date();
        const timeString = now.toLocaleTimeString();
        document.getElementById('lastUpdate').textContent = timeString;
        document.getElementById('lastHealthCheck').textContent = now.toLocaleString();
    }
    
    filterTable(searchTerm) {
        const rows = document.querySelectorAll('#accountsTableBody tr:not(.no-data)');
        const term = searchTerm.toLowerCase();
        
        rows.forEach(row => {
            const account = row.dataset.account;
            const text = row.textContent.toLowerCase();
            const matches = text.includes(term);
            row.style.display = matches ? '' : 'none';
        });
    }
    
    async copyWebhookUrl() {
        if (!this.webhookUrl) {
            this.showToast('Webhook URL not available', 'warning');
            return;
        }
        
        try {
            await navigator.clipboard.writeText(this.webhookUrl);
            this.showToast('Webhook URL copied to clipboard!', 'success');
        } catch (error) {
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = this.webhookUrl;
            document.body.appendChild(textArea);
            textArea.select();
            
            try {
                document.execCommand('copy');
                this.showToast('Webhook URL copied to clipboard!', 'success');
            } catch (fallbackError) {
                this.showToast('Failed to copy webhook URL', 'error');
            }
            
            document.body.removeChild(textArea);
        }
    }
    
    showToast(message, type = 'info', duration = 5000) {
        const container = document.getElementById('toastContainer');
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        
        const icons = {
            success: 'check-circle',
            error: 'exclamation-circle',
            warning: 'exclamation-triangle',
            info: 'info-circle'
        };
        
        const titles = {
            success: 'Success',
            error: 'Error',
            warning: 'Warning',
            info: 'Information'
        };
        
        toast.innerHTML = `
            <div class="toast-icon">
                <i class="fas fa-${icons[type]}"></i>
            </div>
            <div class="toast-content">
                <div class="toast-title">${titles[type]}</div>
                <div class="toast-message">${message}</div>
            </div>
            <button class="toast-close" onclick="this.parentElement.remove()">
                <i class="fas fa-times"></i>
            </button>
        `;
        
        container.appendChild(toast);
        
        // Auto remove after duration
        setTimeout(() => {
            if (toast.parentElement) {
                toast.remove();
            }
        }, duration);
    }
    
    showConfirmDialog(title, message) {
        return new Promise((resolve) => {
            const modal = document.getElementById('modalOverlay');
            const titleElement = document.getElementById('modalTitle');
            const messageElement = document.getElementById('modalMessage');
            const confirmBtn = document.getElementById('modalConfirmBtn');
            
            titleElement.textContent = title;
            messageElement.textContent = message;
            
            modal.classList.add('show');
            
            // Store resolve function for later use
            this.currentAction = resolve;
        });
    }
    
    closeModal() {
        const modal = document.getElementById('modalOverlay');
        modal.classList.remove('show');
        
        if (this.currentAction) {
            this.currentAction(false);
            this.currentAction = null;
        }
    }
    
    confirmAction() {
        if (this.currentAction) {
            this.currentAction(true);
            this.currentAction = null;
        }
        this.closeModal();
    }
    
    showLoading() {
        document.getElementById('loadingOverlay').classList.add('show');
    }
    
    hideLoading() {
        document.getElementById('loadingOverlay').classList.remove('show');
    }
    
    startAutoRefresh() {
        // Refresh every 30 seconds
        this.refreshInterval = setInterval(() => {
            if (!document.hidden) {
                this.loadData();
            }
        }, 30000);
    }
    
    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }
    
    formatDate(dateString) {
        const date = new Date(dateString);
        const now = new Date();
        const diffTime = Math.abs(now - date);
        const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
        
        if (diffDays === 0) {
            return 'Today ' + date.toLocaleTimeString();
        } else if (diffDays === 1) {
            return 'Yesterday ' + date.toLocaleTimeString();
        } else if (diffDays < 7) {
            return `${diffDays} days ago`;
        } else {
            return date.toLocaleDateString();
        }
    }
    
    // Health check function
    async checkHealth() {
        try {
            const response = await fetch('/health');
            const data = await response.json();
            
            if (data.ok) {
                document.getElementById('serverStatus').textContent = 'Online';
                document.getElementById('serverStatus').className = 'status-badge online';
            } else {
                document.getElementById('serverStatus').textContent = 'Warning';
                document.getElementById('serverStatus').className = 'status-badge warning';
            }
        } catch (error) {
            document.getElementById('serverStatus').textContent = 'Offline';
            document.getElementById('serverStatus').className = 'status-badge offline';
        }
    }
    
    // Cleanup when page unloads
    cleanup() {
        this.stopAutoRefresh();
    }
}

// Global functions for onclick events
function copyWebhookUrl() {
    if (window.ui) {
        window.ui.copyWebhookUrl();
    }
}

function closeModal() {
    if (window.ui) {
        window.ui.closeModal();
    }
}

function confirmAction() {
    if (window.ui) {
        window.ui.confirmAction();
    }
}

// Initialize UI when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.ui = new TradingBotUI();
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (window.ui) {
        window.ui.cleanup();
    }
});

// Handle online/offline events
window.addEventListener('online', () => {
    if (window.ui) {
        window.ui.showToast('Connection restored', 'success');
        window.ui.loadData();
    }
});

window.addEventListener('offline', () => {
    if (window.ui) {
        window.ui.showToast('Connection lost', 'warning');
    }
});

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + R for refresh
    if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
        e.preventDefault();
        if (window.ui) {
            window.ui.loadData();
        }
    }
    
    // Ctrl/Cmd + K for search focus
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        const searchInput = document.getElementById('searchInput');
        if (searchInput) {
            searchInput.focus();
        }
    }
});