// MT5 Trading Bot Frontend JavaScript (with icon-only Theme Toggle)
class TradingBotUI {
  constructor() {
    this.accounts = [];
    this.webhookUrl = '';
    this.currentAction = null;
    this.refreshInterval = null;
    this.currentExampleIndex = 0;

    this.tradeHistory = [];
    this.maxHistoryItems = 100;
    this._es = null;

    // JSON Examples
this.jsonExamples = [
  {
    title: "Market:",
    json: `{
  "account_number": "1123456",
  "symbol": "XAUUSD",
  "action": "BUY",
  "volume": 0.01,
  "take_profit": 2450.0,
  "stop_loss": 2400.0,
  "comment": "TV-Signal"
}`
  },
  {
    title: "Market 2:",
    json: `{
  "account_number": "xxxx",
  "symbol": "{{ticker}}",
  "action": "{{strategy.order.comment}}",
  "volume": "{{strategy.order.contracts}}"
}`
  },
  {
    title: "Limit:",
    json: `{
  "account_number": "1123456",
  "symbol": "EURUSD",
  "action": "SELL",
  "order_type": "limit",
  "price": 1.0950,
  "volume": 0.1
}`
  },
  {
    title: "Limit 2:",
    json: `{
  "account_number": "xxxx",
  "symbol": "{{ticker}}",
  "action": "{{strategy.order.comment}}",
  "order_type": "limit",
  "price": 2425,
  "take_profit": 2450,
  "stop_loss": 2400.0,
  "volume": "{{strategy.order.contracts}}"
}`
  },
  {
    title: "Close:",
    json: `{
  "account_number": "1123456",
  "symbol": "XAUUSD",
  "order_type": "close"
}`
  },
  {
    title: "Close 2:",
    json: `{
  "account_number": "xxxx",
  "symbol": "{{ticker}}",
  "action": "close",
  "volume": "{{strategy.order.contracts}}"
}`
  }
];

    this.init();
  }

  /* ---------- Theme ---------- */
  initTheme() {
    const saved = localStorage.getItem('theme');
    const pref = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    this.setTheme(saved || pref || 'dark');
  }

  setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);
    this.updateThemeToggleUI();
  }

  toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'dark';
    this.setTheme(current === 'dark' ? 'light' : 'dark');
  }

  updateThemeToggleUI() {
    const btn = document.getElementById('themeToggleBtn');
    if (!btn) return;
    const theme = document.documentElement.getAttribute('data-theme') || 'dark';
    if (theme === 'dark') {
      btn.innerHTML = '<i class="fas fa-sun"></i>';
      btn.classList.remove('btn-primary'); btn.classList.add('btn-secondary');
      btn.setAttribute('aria-label','โหมดสว่าง'); btn.setAttribute('title','โหมดสว่าง');
    } else {
      btn.innerHTML = '<i class="fas fa-moon"></i>';
      btn.classList.remove('btn-secondary'); btn.classList.add('btn-primary');
      btn.setAttribute('aria-label','โหมดมืด'); btn.setAttribute('title','โหมดมืด');
    }
  }

  init() {
    this.initTheme();
    this.setupEventListeners();
    this.loadData();
    this.startAutoRefresh();
    this.updateLastUpdateTime();
    this.showExample(0);

    this.renderHistory();
    this.loadInitialHistoryFromServer().then(() => {
      this.subscribeTradeEvents();
    });
  }

  setupEventListeners() {
    const themeBtn = document.getElementById('themeToggleBtn');
    if (themeBtn) themeBtn.addEventListener('click', () => this.toggleTheme());

    document.getElementById('addAccountForm').addEventListener('submit', (e) => {
      e.preventDefault();
      this.addAccount();
    });

    document.getElementById('refreshBtn').addEventListener('click', () => this.loadData());

    document.getElementById('webhookBtn').addEventListener('click', () => this.copyWebhookUrl());

    document.getElementById('searchInput').addEventListener('input', (e) => {
      this.filterTable(e.target.value);
    });

    document.addEventListener('click', (e) => {
      if (e.target.classList.contains('modal-overlay')) this.closeModal();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this.closeModal();
      if (e.target.closest('.example-section')) {
        if (e.key === 'ArrowLeft') this.showExample(Math.max(0, this.currentExampleIndex - 1));
        if (e.key === 'ArrowRight') this.showExample(Math.min(this.jsonExamples.length - 1, this.currentExampleIndex + 1));
      }
    });

    document.addEventListener('visibilitychange', () => { if (!document.hidden) this.loadData(); });

    window.addEventListener('online', () => { this.showToast('Connection restored', 'success'); this.loadData(); });
    window.addEventListener('offline', () => { this.showToast('Connection lost', 'warning'); });

    const historyFilter = document.getElementById('historyFilter');
    if (historyFilter) historyFilter.addEventListener('change', () => {
      this.renderHistory();
    });
  }

  /* ---------- Data ---------- */
  async loadData() {
    try {
      this.showLoading();
      const [accountsResponse, webhookResponse] = await Promise.all([
        fetch('/accounts'),
        fetch('/webhook-url')
      ]);

      if (accountsResponse.ok) {
        const accountsData = await accountsResponse.json();
        this.accounts = accountsData.accounts || [];
        this.updateAccountsTable();
        this.updateStats();
      }

      if (webhookResponse.ok) {
        const webhookData = await webhookResponse.json();
        this.webhookUrl = webhookData.url || '';
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
    const account = String(formData.get('account') || '').trim();
    const nickname = String(formData.get('nickname') || '').trim();

    if (!account) {
      this.showToast('Please enter account number', 'warning');
      return;
    }

    try {
      this.showLoading();
      const response = await fetch('/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
    if (confirmMessage && !await this.showConfirmDialog('Confirm Action', confirmMessage)) return;

    try {
      this.showLoading();
      let endpoint = `/accounts/${account}/${action}`;
      let method = 'POST';
      if (action === 'delete') { endpoint = `/accounts/${account}`; method = 'DELETE'; }

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

  /* ---------- UI Helpers ---------- */
  showExample(index) {
    this.currentExampleIndex = index;
    const example = this.jsonExamples[index];
    document.querySelectorAll('.example-nav-btn').forEach((btn, i) => {
      btn.classList.toggle('active', i === index);
    });
    document.getElementById('exampleTitle').textContent = example.title;
    document.getElementById('jsonCode').textContent = example.json;
  }

  copyExample() {
    const jsonCode = document.getElementById('jsonCode').textContent;
    this.copyToClipboard(jsonCode, 'JSON example copied to clipboard!');
  }

  updateAccountsTable() {
    const tbody = document.getElementById('accountsTableBody');

    if (!this.accounts.length) {
      tbody.innerHTML = `
        <tr class="no-data">
          <td colspan="6">
            <div class="no-data-message">
              <i class="fas fa-inbox"></i>
              <p>No accounts found. Add your first account above.</p>
            </div>
          </td>
        </tr>`;
      return;
    }

    tbody.innerHTML = this.accounts.map(account => {
      const createdDate = new Date(account.created).toLocaleString();
      const statusClass = (account.status || 'Offline').toLowerCase();

      return `
        <tr data-account="${account.account}">
          <td>
            <span class="status-badge ${statusClass}">
              <i class="fas fa-circle"></i>
              ${account.status}
            </span>
          </td>
          <td><strong>${account.account}</strong></td>
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
        </tr>`;
    }).join('');
  }

  updateStats() {
    const total = this.accounts.length;
    const online = this.accounts.filter(acc => acc.status === 'Online').length;
    const offline = total - online;

    document.getElementById('totalAccounts').textContent = total;
    document.getElementById('onlineAccounts').textContent = online;
    document.getElementById('offlineAccounts').textContent = offline;

    document.getElementById('serverStatus').textContent = 'Online';
    document.getElementById('serverStatus').className = 'status-badge online';
  }

  updateWebhookDisplay() {
    const webhookElement = document.getElementById('webhookUrl');
    const webhookEndpointElement = document.getElementById('webhookEndpoint');
    if (webhookElement && this.webhookUrl) webhookElement.value = this.webhookUrl;
    if (webhookEndpointElement && this.webhookUrl) webhookEndpointElement.textContent = this.webhookUrl;
  }

  updateLastUpdateTime() {
    const now = new Date();
    const timeString = now.toLocaleTimeString();
    document.getElementById('lastUpdate').textContent = timeString;
    const hc = document.getElementById('lastHealthCheck');
    if (hc) hc.textContent = now.toLocaleString();
  }

  filterTable(searchTerm) {
    const rows = document.querySelectorAll('#accountsTableBody tr:not(.no-data)');
    const term = String(searchTerm || '').toLowerCase();
    rows.forEach(row => {
      const text = row.textContent.toLowerCase();
      row.style.display = text.includes(term) ? '' : 'none';
    });
  }

  async copyWebhookUrl() {
    if (!this.webhookUrl) {
      this.showToast('Webhook URL not available', 'warning');
      return;
    }
    this.copyToClipboard(this.webhookUrl, 'Webhook URL copied to clipboard!');
  }

  async copyToClipboard(text, successMessage) {
    try {
      await navigator.clipboard.writeText(text);
      this.showToast(successMessage, 'success');
    } catch {
      const textArea = document.createElement('textarea');
      textArea.value = text;
      document.body.appendChild(textArea);
      textArea.select();
      try {
        document.execCommand('copy');
        this.showToast(successMessage, 'success');
      } catch {
        this.showToast('Failed to copy to clipboard', 'error');
      }
      document.body.removeChild(textArea);
    }
  }

  showToast(message, type = 'info', duration = 5000) {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const icons = { success:'check-circle', error:'exclamation-circle', warning:'exclamation-triangle', info:'info-circle' };
    const titles = { success:'Success', error:'Error', warning:'Warning', info:'Information' };
    toast.innerHTML = `
      <div class="toast-icon"><i class="fas fa-${icons[type]}"></i></div>
      <div class="toast-content">
        <div class="toast-title">${titles[type]}</div>
        <div class="toast-message">${message}</div>
      </div>
      <button class="toast-close" onclick="this.parentElement.remove()"><i class="fas fa-times"></i></button>`;
    container.appendChild(toast);
    setTimeout(() => { if (toast.parentElement) toast.remove(); }, duration);
  }

  showConfirmDialog(title, message) {
    return new Promise((resolve) => {
      const modal = document.getElementById('modalOverlay');
      document.getElementById('modalTitle').textContent = title;
      document.getElementById('modalMessage').textContent = message;
      modal.classList.add('show');
      const confirmBtn = document.getElementById('modalConfirmBtn');
      const handler = () => { resolve(true); cleanup(); };
      const cleanup = () => {
        confirmBtn.removeEventListener('click', handler);
        this.closeModal();
      };
      confirmBtn.addEventListener('click', handler, { once: true });
      this.currentAction = (ok) => { resolve(!!ok); cleanup(); };
    });
  }

  closeModal() {
    const modal = document.getElementById('modalOverlay');
    modal.classList.remove('show');
    if (this.currentAction) { this.currentAction(false); this.currentAction = null; }
  }

  confirmAction() {
    if (this.currentAction) { this.currentAction(true); this.currentAction = null; }
    this.closeModal();
  }

  showLoading() { document.getElementById('loadingOverlay').classList.add('show'); }
  hideLoading() { document.getElementById('loadingOverlay').classList.remove('show'); }

  startAutoRefresh() {
    this.refreshInterval = setInterval(() => {
      if (!document.hidden) this.loadData();
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
    if (isNaN(date)) return '-';
    const now = new Date();
    const diff = now - date;
    const day = 1000*60*60*24;
    const d = Math.floor(diff / day);
    if (d === 0) return 'Today ' + date.toLocaleTimeString();
    if (d === 1) return 'Yesterday ' + date.toLocaleTimeString();
    if (d < 7) return `${d} days ago`;
    return date.toLocaleDateString();
  }

  async checkHealth() {
    try {
      const response = await fetch('/health');
      const data = await response.json();
      if (data.ok) {
        document.getElementById('serverStatus').textContent = 'Online';
        document.getElementById('serverStatus').className = 'status-badge online';
      } else {
        document.getElementById('serverStatus').textContent = 'Warning';
        document.getElementById('serverStatus').className = 'status-badge loading';
      }
    } catch {
      document.getElementById('serverStatus').textContent = 'Offline';
      document.getElementById('serverStatus').className = 'status-badge offline';
    }
  }

  async loadInitialHistoryFromServer() {
    try {
      const res = await fetch('/trades?limit=100');
      if (!res.ok) return;
      const data = await res.json();
      const arr = Array.isArray(data.trades) ? data.trades : [];
      arr.reverse().forEach(tr => this.addTradeToHistory(tr));
    } catch (e) {
      console.warn('loadInitialHistoryFromServer failed:', e);
    }
  }

  subscribeTradeEvents() {
    if (!('EventSource' in window)) return;
    try {
      if (this._es) { try { this._es.close(); } catch {} }
      const es = new EventSource('/events/trades');
      es.onmessage = (evt) => {
        try {
          const tr = JSON.parse(evt.data);
          this.addTradeToHistory(tr);
        } catch (e) { console.warn('Invalid trade event:', e); }
      };
      es.onerror = () => {};
      this._es = es;
    } catch (e) {
      console.warn('SSE unavailable', e);
    }
  }

  addTradeToHistory(tr) {
    const norm = {
      id: tr.id || String(Date.now()),
      status: (tr.status || '').toLowerCase() === 'error' ? 'error' : 'success',
      action: (tr.action || '').toUpperCase(),
      symbol: tr.symbol || '-',
      account: tr.account || tr.account_number || '-',
      volume: tr.volume ?? '',
      price: tr.price ?? '',
      message: tr.message || '',
      timestamp: tr.timestamp || new Date().toISOString(),
    };
    const idx = this.tradeHistory.findIndex(x => x.id === norm.id);
    if (idx !== -1) this.tradeHistory.splice(idx, 1);
    this.tradeHistory.unshift(norm);
    if (this.tradeHistory.length > this.maxHistoryItems) {
      this.tradeHistory.pop();
    }
    this.renderHistory();
  }

  renderHistory() {
    const tbody = document.getElementById('historyTableBody');
    if (!tbody) return;
    const filterEl = document.getElementById('historyFilter');
    const filter = (filterEl?.value || 'all').toLowerCase();
    const list = this.tradeHistory.filter(t => {
      if (filter === 'success') return t.status === 'success';
      if (filter === 'error')   return t.status === 'error';
      return true;
    });
    if (!list.length) {
      tbody.innerHTML = `
        <tr class="no-data">
          <td colspan="8">
            <div class="no-data-message">
              <i class="fas fa-clock-rotate-left"></i>
              <p>No trading history yet. Trades will appear here when executed.</p>
            </div>
          </td>
        </tr>`;
      return;
    }
    tbody.innerHTML = list.map(t => {
      const time = new Date(t.timestamp).toLocaleString();
      const badge = t.status === 'success' ? 'online' : 'offline';
      return `
        <tr>
          <td><span class="status-badge ${badge}">${t.status}</span></td>
          <td>${this.escape(t.action)}</td>
          <td>${this.escape(t.symbol)}</td>
          <td>${this.escape(t.account)}</td>
          <td>${this.escape(t.volume)}</td>
          <td>${this.escape(t.price)}</td>
          <td>${this.escape(t.message)}</td>
          <td>${this.escape(time)}</td>
        </tr>`;
    }).join('');
  }

  escape(v) {
    return String(v ?? '').replace(/[&<>"]/g, s => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'
    }[s]));
  }

  // <<< Added: Clear history >>>
  async clearHistory() {
    const ok = await this.showConfirmDialog('Clear Trading History', 'Delete all saved trade history? This cannot be undone.');
    if (!ok) return;

    // ลองลบที่ฝั่งเซิร์ฟเวอร์ก่อน (ถ้ามี endpoint รองรับ)
    let serverCleared = false;
    try {
      const res = await fetch('/trades/clear', { method: 'POST' });
      serverCleared = res.ok;
    } catch (_) { /* ignore */ }

    // ไม่ว่าฝั่งเซิร์ฟเวอร์จะลบได้รึเปล่า เคลียร์ฝั่ง UI ให้เสร็จ
    this.tradeHistory = [];
    this.renderHistory();

    this.showToast(serverCleared ? 'History cleared.' : 'History cleared locally.', 'success');
  }
  // >>> end

  cleanup() { 
    this.stopAutoRefresh(); 
    if (this._es) { try { this._es.close(); } catch {} }
  }
}

/* Helpers for inline onclick */
function showExample(i){ if (window.ui) window.ui.showExample(i); }
function copyExample(){ if (window.ui) window.ui.copyExample(); }
function copyWebhookUrl(){ if (window.ui) window.ui.copyWebhookUrl(); }
function closeModal(){ if (window.ui) window.ui.closeModal(); }
function confirmAction(){ if (window.ui) window.ui.confirmAction(); }

/* Boot */
document.addEventListener('DOMContentLoaded', () => { window.ui = new TradingBotUI(); });
window.addEventListener('beforeunload', () => { if (window.ui) window.ui.cleanup(); });
