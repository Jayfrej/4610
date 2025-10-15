

// MT5 Trading Bot Frontend JavaScript with Copy Trading
class TradingBotUI {
  constructor() {
    this.accounts = [];
    this.webhookAccounts = []; // separate list for Webhook Management
    this.webhookUrl = '';
    this.currentAction = null;
    this.refreshInterval = null;
    this.currentExampleIndex = 0;
    this.tradeHistory = [];
    this.maxHistoryItems = 100;
    this._es = null;

    // Copy Trading
    this.copyPairs = [];
    this.copyHistory = [];
    this.maxCopyHistory = 100;
    this._copyEs = null;
    this.currentPage = 'accounts';

    // Plans
    this.plans = [];

    // Master and Slave Accounts
    this.masterAccounts = [];
    this.slaveAccounts = [];

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

  async ensureLogin() {
    if (sessionStorage.getItem('tab-auth') === '1') return;
    const u = prompt('Username:');
    const p = prompt('Password:');
    if (!u || !p) { location.reload(); return; }

    const res = await fetch('/login', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ username: u, password: p })
    });

    if (!res.ok) {
      alert('Login failed');
      location.reload();
      return;
    }
    sessionStorage.setItem('tab-auth', '1');
  }

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
      btn.classList.remove('btn-primary');
      btn.classList.add('btn-secondary');
    } else {
      btn.innerHTML = '<i class="fas fa-moon"></i>';
      btn.classList.remove('btn-secondary');
      btn.classList.add('btn-primary');
    }
  }

  init() {
    this.initTheme();
    this.setupEventListeners();

    this.ensureLogin().then(() => {
      // Set default page to Account Management
      this.currentPage = 'accounts';
      
      // Show Account Management page as default
      this.switchPage('accounts');
      
      this.loadData();
      this.startAutoRefresh();
      this.updateLastUpdateTime();
      this.showExample(0);
      this.renderHistory();
      this.loadInitialHistoryFromServer().then(() => {
        this.updateAccountFilterOptions();
        this.subscribeTradeEvents();
      });

      // Load Copy Trading data
      this.loadCopyPairs();
      this.loadCopyHistory();
      this.subscribeCopyEvents();
      this.loadPlans();
      this.renderPlans();
      this.loadMasterAccounts();
      this.loadSlaveAccounts();
      this.renderMasterAccounts();
      this.renderSlaveAccounts();
    });
  }

  setupEventListeners() {
    const themeBtn = document.getElementById('themeToggleBtn');
    if (themeBtn) themeBtn.addEventListener('click', () => this.toggleTheme());

    // Sidebar navigation
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
      item.addEventListener('click', (e) => {
        e.preventDefault();
        const page = item.dataset.page;
        this.switchPage(page);
      });
    });

    // Sidebar toggle for mobile
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');
    if (sidebarToggle && sidebar) {
      sidebarToggle.addEventListener('click', () => {
        sidebar.classList.toggle('show');
      });
    }

    // Sidebar collapse button
    const sidebarCollapseBtn = document.getElementById('sidebarCollapseBtn');
    if (sidebarCollapseBtn && sidebar) {
      sidebarCollapseBtn.addEventListener('click', () => {
        sidebar.classList.toggle('collapsed');
      });
    }

    const addForm = document.getElementById('addAccountForm');
    if (addForm) {
      addForm.addEventListener('submit', (e) => {
        e.preventDefault();
        this.addAccount();
      });
    }

    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) refreshBtn.addEventListener('click', () => this.loadData());

    const webhookBtn = document.getElementById('webhookBtn');
    if (webhookBtn) webhookBtn.addEventListener('click', () => this.copyWebhookUrl());

    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        this.filterTable(e.target.value);
      });
    }

    const searchInputAM = document.getElementById('searchInputAM');
    if (searchInputAM) {
      searchInputAM.addEventListener('input', (e) => {
        this.filterTableAM(e.target.value);
      });
    }

    const addFormAM = document.getElementById('addAccountFormAM');
    if (addFormAM) {
      addFormAM.addEventListener('submit', (e) => {
        e.preventDefault();
        this.addAccountAM();
      });
    }

    document.addEventListener('click', (e) => {
      if (e.target.classList.contains('modal-overlay')) this.closeModal();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this.closeModal();
    });

    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) {
        this.loadData();
        if (this.currentPage === 'copytrading') {
          this.loadCopyPairs();
        }
      }
    });

    window.addEventListener('online', () => {
      this.showToast('Connection restored', 'success');
      this.loadData();
    });

    window.addEventListener('offline', () => {
      this.showToast('Connection lost', 'warning');
    });

    const historyFilter = document.getElementById('historyFilter');
    if (historyFilter) historyFilter.addEventListener('change', () => this.renderHistory());

    const accountFilter = document.getElementById('accountFilter');
    if (accountFilter) accountFilter.addEventListener('change', () => this.renderHistory());

    const copyHistoryFilter = document.getElementById('copyHistoryFilter');
    if (copyHistoryFilter) copyHistoryFilter.addEventListener('change', () => this.renderCopyHistory());
  

    const copyEndpointBtn = document.getElementById('copyEndpointBtn');
    if (copyEndpointBtn) {
      copyEndpointBtn.addEventListener('click', () => this.copyCopyTradingEndpoint());
    }
    const copyEndpointBtnSystem = document.getElementById('copyEndpointBtnSystem');
    if (copyEndpointBtnSystem) {
      copyEndpointBtnSystem.addEventListener('click', () => this.copyCopyTradingEndpoint());
    }

}

  switchPage(page) {
    this.currentPage = page;
    
    // Update navigation
    document.querySelectorAll('.nav-item').forEach(item => {
      item.classList.toggle('active', item.dataset.page === page);
    });

    // Update page content
    document.querySelectorAll('.page-content').forEach(content => {
      content.classList.toggle('active', content.id === `page-${page}`);
    });

    // Update header
    const headerContent = document.getElementById('headerContent');
    if (headerContent) {
      if (page === 'accounts') {
        headerContent.innerHTML = '<h1><i class="fas fa-table"></i> Account Management</h1><p>Manage your MT5 trading accounts</p>';
      } else if (page === 'webhook') {
        headerContent.innerHTML = '<h1><i class="fas fa-robot"></i> MT5 Trading Bot</h1><p>Multi-Account Webhook Manager</p>';
      } else if (page === 'copytrading') {
        headerContent.innerHTML = '<h1><i class="fas fa-copy"></i> Copy Trading</h1><p>Master-Slave Account Management</p>';
      } else if (page === 'system') {
        headerContent.innerHTML = '<h1><i class="fas fa-info-circle"></i> System Information</h1><p>Server status and configuration</p>';
      }
    }

    // Hide sidebar on mobile after selection
    const sidebar = document.getElementById('sidebar');
    if (sidebar && window.innerWidth <= 1024) {
      sidebar.classList.remove('show');
    }

    // Load data for Account Management page
    if (page === 'accounts') {
      this.loadAccountManagementData();
    }
  
    if (page === 'copytrading') {
      this.loadData().then(() => {
        this.renderMasterAccounts();
        this.renderSlaveAccounts();
      });
      this.loadCopyPairs();
      this.loadCopyHistory();
    }

}
async loadData() {
    try {
      this.showLoading();
      const [accountsResponse, webhookUrlResponse, webhookAccountsResponse] = await Promise.all([
        fetch('/accounts'),
        fetch('/webhook-url'),
        fetch('/webhook-accounts').catch(() => null)
      ]);

      if (accountsResponse && accountsResponse.ok) {
        const accountsData = await accountsResponse.json();
        this.accounts = accountsData.accounts || [];
        // Update Account Management (server-backed)
        this.updateAccountsTableAM();
        this.updateStatsAM();
      }

      // Webhook accounts (separate list)
      if (webhookAccountsResponse && webhookAccountsResponse.ok) {
        const waData = await webhookAccountsResponse.json();
        this.webhookAccounts = Array.isArray(waData.accounts) ? waData.accounts : [];
      } else {
        // Fallback to localStorage for webhook accounts
        const saved = localStorage.getItem('mt5_webhook_accounts');
        this.webhookAccounts = saved ? JSON.parse(saved) : [];
      }
      // Update Webhook page
      this.updateAccountsTable();
      this.updateStats();
      this.updateAccountFilterOptions();

      if (webhookUrlResponse && webhookUrlResponse.ok) {
        const webhookData = await webhookUrlResponse.json();
        this.webhookUrl = webhookData.url || '';
        this.updateWebhookDisplay();
      }

      this.updateLastUpdateTime();
      // Don't show toast on auto-refresh
    } catch (error) {
      console.error('Failed to load data:', error);
      this.showToast('Failed to load data', 'error');
    } finally {
      this.hideLoading();
    }
  }

  // Account Management Page Functions
  async loadAccountManagementData() {
    try {
      const response = await fetch('/accounts');
      if (response.ok) {
        const data = await response.json();
        this.accounts = data.accounts || [];
        this.updateAccountsTableAM();
        this.updateStatsAM();
      }
    } catch (error) {
      console.error('Failed to load account management data:', error);
    }
  }

  async addAccountAM() {
    const formData = new FormData(document.getElementById('addAccountFormAM'));
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
        document.getElementById('addAccountFormAM').reset();
        this.loadAccountManagementData();
        this.loadData(); // Also update webhook page
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

  async addAccountFromServerAM() {
    this.showToast('Add from Server feature - API not yet implemented', 'warning');
  }

  updateAccountsTableAM() {
    const tbody = document.getElementById('accountsTableBodyAM');
    if (!tbody) return;

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
                <button class="btn btn-warning btn-sm" onclick="ui.performAccountActionAM('${account.account}', 'restart')" title="Restart">
                  <i class="fas fa-redo"></i>
                </button>
                <button class="btn btn-danger btn-sm" onclick="ui.performAccountActionAM('${account.account}', 'stop')" title="Stop">
                  <i class="fas fa-stop"></i>
                </button>
              ` : `
                <button class="btn btn-success btn-sm" onclick="ui.performAccountActionAM('${account.account}', 'open')" title="Open">
                  <i class="fas fa-play"></i>
                </button>
              `}
              <button class="btn btn-secondary btn-sm" onclick="ui.performAccountActionAM('${account.account}', 'delete')" title="Delete">
                <i class="fas fa-trash"></i>
              </button>
            </div>
          </td>
        </tr>`;
    }).join('');
  }

  updateStatsAM() {
    const total = this.accounts.length;
    const online = this.accounts.filter(acc => acc.status === 'Online').length;
    const offline = total - online;

    const totalEl = document.getElementById('totalAccountsAM');
    const onlineEl = document.getElementById('onlineAccountsAM');
    const offlineEl = document.getElementById('offlineAccountsAM');

    if (totalEl) totalEl.textContent = total;
    if (onlineEl) onlineEl.textContent = online;
    if (offlineEl) offlineEl.textContent = offline;
  }

  async performAccountActionAM(account, action) {
    let confirmMessage = '';
    if (action === 'restart') {
      confirmMessage = 'Are you sure you want to restart this account?';
    } else if (action === 'stop') {
      confirmMessage = 'Are you sure you want to stop this account?';
    } else if (action === 'delete') {
      confirmMessage = 'WARNING: This will permanently delete the account from the server and remove all instance files. This action cannot be undone. Continue?';
    }

    if (confirmMessage && !await this.showConfirmDialog('Confirm Action', confirmMessage)) return;

    try {
      this.showLoading();
      let endpoint = `/accounts/${account}/${action}`;
      let method = 'POST';
      if (action === 'delete') {
        // Real server deletion - removes instance folder
        endpoint = `/accounts/${account}`;
        method = 'DELETE';
      }

      const response = await fetch(endpoint, { method });
      const data = await response.json();

      if (response.ok) {
        this.showToast(`Account ${action} successful`, 'success');
        this.loadAccountManagementData();
        this.loadData(); // Also update webhook page
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

  filterTableAM(searchTerm) {
    const rows = document.querySelectorAll('#accountsTableBodyAM tr:not(.no-data)');
    const term = String(searchTerm || '').toLowerCase();
    rows.forEach(row => {
      const text = row.textContent.toLowerCase();
      row.style.display = text.includes(term) ? '' : 'none';
    });
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

  async addAccountFromServer() {
    try {
      const response = await fetch('/accounts');
      if (!response.ok) {
        throw new Error('Failed to fetch accounts from server');
      }
      
      const data = await response.json();
      const accounts = data.accounts || [];
      
      if (accounts.length === 0) {
        this.showToast('No accounts found on server', 'warning');
        return;
      }
      
      // Filter out accounts already in current page
      const currentAccountNumbers = new Set((this.webhookAccounts || []).map(a => a.account || a.id));
      const availableAccounts = accounts.filter(acc => !currentAccountNumbers.has(acc.account));
      
      if (availableAccounts.length === 0) {
        this.showToast('All server accounts are already added to this page', 'info');
        return;
      }
      
      // Show selection modal for webhook page
      this.showAccountSelectionModalForWebhook(availableAccounts);
      
    } catch (error) {
      console.error('Failed to fetch accounts from server:', error);
      this.showToast('Failed to load accounts from server', 'error');
    }
  }

  updateAccountsTable() {
  const tbody = document.getElementById('accountsTableBody');
  if (!tbody) return;

  const list = this.webhookAccounts || [];

  if (!list.length) {
    tbody.innerHTML = `
      <tr class="no-data">
        <td colspan="6">
          <div class="no-data-message">
            <i class="fas fa-inbox"></i>
            <p>No webhook accounts. Use "Add from Server" to add.</p>
          </div>
        </td>
      </tr>`;
    return;
  }

  tbody.innerHTML = list.map(webhookAccount => {
    const accNumber = webhookAccount.account || webhookAccount.id || '';
    
    // ✅ หาข้อมูลจาก Server Accounts (ถ้ามี)
    const serverAccount = this.accounts.find(a => String(a.account) === String(accNumber));
    
    // ✅ ใช้ข้อมูลจาก Server ถ้ามี, ไม่งั้นใช้จาก localStorage
    const status = serverAccount?.status || 'Unknown';
    const pid = serverAccount?.pid || '-';
    const created = serverAccount?.created || webhookAccount.created || '-';
    const nickname = serverAccount?.nickname || webhookAccount.nickname || '-';
    
    const statusClass = status.toLowerCase();
    const createdDate = created !== '-' ? new Date(created).toLocaleString() : '-';

    return `
      <tr data-account="${this.escape(accNumber)}">
        <td>
          <span class="status-badge ${this.escape(statusClass)}">
            <i class="fas fa-circle"></i>
            ${this.escape(status)}
          </span>
        </td>
        <td><strong>${this.escape(accNumber)}</strong></td>
        <td>${this.escape(nickname)}</td>
        <td>${this.escape(pid)}</td>
        <td title="${this.escape(createdDate)}">${this.escape(this.formatDate ? this.formatDate(created) : (createdDate || '-'))}</td>
        <td>
          <div class="action-buttons">
            ${status === 'Online' ? `
              <button class="btn btn-warning btn-sm" onclick="ui.performAccountAction('${this.escape(accNumber)}', 'restart', 'Are you sure you want to restart this account?')" title="Restart">
                <i class="fas fa-redo"></i>
              </button>
              <button class="btn btn-danger btn-sm" onclick="ui.performAccountAction('${this.escape(accNumber)}', 'stop', 'Are you sure you want to stop this account?')" title="Stop">
                <i class="fas fa-stop"></i>
              </button>
            ` : status === 'Offline' ? `
              <button class="btn btn-success btn-sm" onclick="ui.performAccountAction('${this.escape(accNumber)}', 'open')" title="Open">
                <i class="fas fa-play"></i>
              </button>
            ` : `
              <button class="btn btn-secondary btn-sm" disabled title="Account not in system">
                <i class="fas fa-question"></i>
              </button>
            `}
            <button class="btn btn-secondary btn-sm" onclick="ui.performAccountAction('${this.escape(accNumber)}', 'delete')" title="Remove from Webhook">
              <i class="fas fa-trash"></i>
            </button>
          </div>
        </td>
      </tr>`;
  }).join('');
}

  updateStats() {
    const list = this.webhookAccounts || [];
    const total = list.length;
    const online = list.filter(acc => acc.status === 'Online').length;
    const offline = total - online;

    const totalEl = document.getElementById('totalAccounts');
    const onlineEl = document.getElementById('onlineAccounts');
    const offlineEl = document.getElementById('offlineAccounts');
    const statusEl = document.getElementById('serverStatus');

    if (totalEl) totalEl.textContent = total;
    if (onlineEl) onlineEl.textContent = online;
    if (offlineEl) offlineEl.textContent = offline;
    if (statusEl) {
      statusEl.className = 'status-dot ' + (online > 0 ? 'online' : 'offline');
      statusEl.textContent = online > 0 ? 'Online' : 'Offline';
    }
  }

  updateWebhookDisplay() {
  const webhookElement = document.getElementById('webhookUrl');
  const webhookElementAM = document.getElementById('webhookUrlAM');
  const webhookEndpointElement = document.getElementById('webhookEndpoint');
  const webhookEndpointSystemElement = document.getElementById('webhookEndpointSystem');
  
  // ✅ อัปเดต Webhook URL
  if (webhookElement && this.webhookUrl) webhookElement.value = this.webhookUrl;
  if (webhookElementAM && this.webhookUrl) webhookElementAM.value = this.webhookUrl;
  if (webhookEndpointElement && this.webhookUrl) webhookEndpointElement.textContent = this.webhookUrl;
  if (webhookEndpointSystemElement && this.webhookUrl) webhookEndpointSystemElement.textContent = this.webhookUrl;
  
  // ✅ อัปเดต Copy Trading Endpoint
  const copyTradingEndpointSystemElement = document.getElementById('copyTradingEndpointSystem');
  if (copyTradingEndpointSystemElement) {
    // แปลง Webhook URL เป็น Copy Trading Endpoint
    try {
      let baseUrl = '';
      if (this.webhookUrl) {
        const url = new URL(this.webhookUrl);
        baseUrl = `${url.protocol}//${url.host}`;
      } else {
        baseUrl = `${window.location.protocol}//${window.location.host}`;
      }
      const copyTradingEndpoint = `${baseUrl}/api/copy/trade`;
      copyTradingEndpointSystemElement.textContent = copyTradingEndpoint;
    } catch (e) {
      copyTradingEndpointSystemElement.textContent = 'Error: Invalid URL';
    }
  }
}

  updateLastUpdateTime() {
    const now = new Date();
    const timeString = now.toLocaleTimeString();
    const fullTimeString = now.toLocaleString();
    
    const lastUpdateEl = document.getElementById('lastUpdate');
    const lastUpdateAMEl = document.getElementById('lastUpdateAM');
    const healthCheckEl = document.getElementById('lastHealthCheck');
    const healthCheckSystemEl = document.getElementById('lastHealthCheckSystem');
    
    if (lastUpdateEl) lastUpdateEl.textContent = timeString;
    if (lastUpdateAMEl) lastUpdateAMEl.textContent = timeString;
    if (healthCheckEl) healthCheckEl.textContent = fullTimeString;
    if (healthCheckSystemEl) healthCheckSystemEl.textContent = fullTimeString;
  }

  filterTable(searchTerm) {
    const rows = document.querySelectorAll('#accountsTableBody tr:not(.no-data)');
    const term = String(searchTerm || '').toLowerCase();
    rows.forEach(row => {
      const text = row.textContent.toLowerCase();
      row.style.display = text.includes(term) ? '' : 'none';
    });
  }

  async performAccountAction(account, action, confirmMessage) {
    // For Webhook page - delete only removes from this page, not from server
    if (action === 'delete') {
      confirmMessage = 'Remove this account from the webhook page? (Account will remain on the server)';
    }

    if (confirmMessage && !await this.showConfirmDialog('Confirm Action', confirmMessage)) return;

    try {
      this.showLoading();

      if (action === 'delete') {
        // Remove from Webhook Management only
        this.webhookAccounts = (this.webhookAccounts || []).filter(acc => (acc.account || acc.id) !== account);
        // Persist delete to server if available; else fallback to localStorage
        const tryDelete = async () => {
          try {
            const res = await fetch(`/webhook-accounts/${encodeURIComponent(account)}`, { method: 'DELETE' });
            if (!res.ok) throw new Error('not ok');
          } catch (e) {
            localStorage.setItem('mt5_webhook_accounts', JSON.stringify(this.webhookAccounts));
          }
        };
        await tryDelete();
        this.updateAccountsTable();
        this.updateStats();
        this.showToast('Account removed from webhook page', 'success');
      } else {
        // For other actions (open, stop, restart), call the server (acts on real account)
        let endpoint = `/accounts/${account}/${action}`;
        let method = 'POST';
        const response = await fetch(endpoint, { method });
        const data = await response.json();

        if (response.ok) {
          this.showToast(`Account ${action} successful`, 'success');
          this.loadData();
        } else {
          this.showToast(data.error || `Failed to ${action} account`, 'error');
        }
      }
    } catch (error) {
      console.error(`Failed to ${action} account:`, error);
      this.showToast(`Failed to ${action} account`, 'error');
    } finally {
      this.hideLoading();
    }
  }


  // Copy Trading Functions
  async loadCopyPairs() {
  try {
    const res = await fetch('/api/pairs');
    if (!res.ok) throw new Error('Failed to load pairs');
    const data = await res.json();

    // ✅ ใช้ข้อมูลจาก server โดยตรง
    this.copyPairs = Array.isArray(data.pairs) ? data.pairs : [];

    // ✅ Sync กับ plans (สำหรับ UI เก่า)
    this.plans = (this.copyPairs || []).map(pair => ({
      id: pair.id,
      masterAccount: pair.master_account || pair.masterAccount,
      slaveAccount: pair.slave_account || pair.slaveAccount,
      masterNickname: pair.master_nickname || pair.masterNickname || '',
      slaveNickname: pair.slave_nickname || pair.slaveNickname || '',
      apiToken: pair.api_key || pair.apiKey,
      status: pair.status || 'active',
      settings: {
        autoMapSymbol: pair.settings?.auto_map_symbol ?? pair.settings?.autoMapSymbol ?? true,
        autoMapVolume: pair.settings?.auto_map_volume ?? pair.settings?.autoMapVolume ?? true,
        copyPSL:      pair.settings?.copy_psl        ?? pair.settings?.copyPSL        ?? true,
        volumeMode:   pair.settings?.volume_mode     || pair.settings?.volumeMode     || 'multiply',
        multiplier:   pair.settings?.multiplier      || 2
      }
    }));

    // ✅ อัปเดต UI
    this.renderCopyPairs?.();
    this.renderPlans?.();
    if (typeof this.renderActivePairsTable === 'function') this.renderActivePairsTable();
  } catch (e) {
    console.error('Load pairs error:', e);
    this.showToast('Failed to load copy trading pairs', 'error');
  }
}

  performCopyAccountAction = async (account, action) => {
    let confirmMessage = '';
    if (action === 'restart') {
      confirmMessage = 'Are you sure you want to restart this account?';
    } else if (action === 'stop') {
      confirmMessage = 'Are you sure you want to stop this account?';
    }

    if (confirmMessage && !await this.showConfirmDialog('Confirm Action', confirmMessage)) return;

    try {
      this.showLoading();
      const endpoint = `/accounts/${account}/${action}`;
      const response = await fetch(endpoint, { method: 'POST' });
      const data = await response.json();

      if (response.ok) {
        this.showToast(`Account ${action} successful`, 'success');
        this.loadData(); // Reload to update status
        // Re-render master and slave accounts to reflect new status
        this.renderMasterAccounts();
        this.renderSlaveAccounts();
      } else {
        this.showToast(data.error || `Failed to ${action} account`, 'error');
      }
    } catch (error) {
      console.error(`Failed to ${action} account:`, error);
      this.showToast(`Failed to ${action} account`, 'error');
    } finally {
      this.hideLoading();
    }
  };

  async addMasterAccount() {
    const accountNumber = document.getElementById('masterAccountNumber')?.value?.trim();
    const nickname = document.getElementById('masterNickname')?.value?.trim();

    if (!accountNumber) {
      this.showToast('Please enter master account number', 'warning');
      return;
    }

    // First, add to server like other pages
    try {
      this.showLoading();
      const response = await fetch('/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account: accountNumber, nickname: nickname })
      });

      const data = await response.json();

      if (response.ok) {
        // Add to master accounts list
        if (!this.masterAccounts.some(a => a.accountNumber === accountNumber)) {
          const masterAccount = {
            id: Date.now().toString(),
            accountNumber: accountNumber,
            nickname: nickname || '',
            created: new Date().toISOString()
          };

          this.masterAccounts.unshift(masterAccount);
          this.saveMasterAccounts();
          this.renderMasterAccounts();
          this.updatePairCount();
        }
        
        document.getElementById('masterAccountNumber').value = '';
        document.getElementById('masterNickname').value = '';
        
        this.showToast('Master account added successfully', 'success');
        this.loadData(); // Refresh accounts data
      } else {
        // If account already exists on server, just add to master list
        if (data.error && data.error.includes('already exists')) {
          if (!this.masterAccounts.some(a => a.accountNumber === accountNumber)) {
            const masterAccount = {
              id: Date.now().toString(),
              accountNumber: accountNumber,
              nickname: nickname || '',
              created: new Date().toISOString()
            };

            this.masterAccounts.unshift(masterAccount);
            this.saveMasterAccounts();
            this.renderMasterAccounts();
            this.updatePairCount();
            
            document.getElementById('masterAccountNumber').value = '';
            document.getElementById('masterNickname').value = '';
            
            this.showToast('Account already on server, added as master account', 'success');
          } else {
            this.showToast('Master account already exists', 'warning');
          }
        } else {
          this.showToast(data.error || 'Failed to add account', 'error');
        }
      }
    } catch (error) {
      console.error('Failed to add master account:', error);
      this.showToast('Failed to add master account', 'error');
    } finally {
      this.hideLoading();
    }
  }

  async addMasterFromServer() {
    try {
      const response = await fetch('/accounts');
      if (!response.ok) {
        throw new Error('Failed to fetch accounts from server');
      }
      
      const data = await response.json();
      const accounts = data.accounts || [];
      
      if (accounts.length === 0) {
        this.showToast('No accounts found on server', 'warning');
        return;
      }
      
      const existingMasterNumbers = new Set(this.masterAccounts.map(a => a.accountNumber));
      const availableAccounts = accounts.filter(acc => !existingMasterNumbers.has(acc.account));
      
      if (availableAccounts.length === 0) {
        this.showToast('All server accounts are already added as master accounts', 'info');
        return;
      }
      
      this.showAccountSelectionModal(availableAccounts, 'master');
      
    } catch (error) {
      console.error('Failed to fetch accounts from server:', error);
      this.showToast('Failed to load accounts from server', 'error');
    }
  }

  async addSlaveAccount() {
    const accountNumber = document.getElementById('slaveAccountNumber')?.value?.trim();
    const nickname = document.getElementById('slaveNickname')?.value?.trim();

    if (!accountNumber) {
      this.showToast('Please enter slave account number', 'warning');
      return;
    }

    // First, add to server like other pages
    try {
      this.showLoading();
      const response = await fetch('/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ account: accountNumber, nickname: nickname })
      });

      const data = await response.json();

      if (response.ok) {
        // Add to slave accounts list
        if (!this.slaveAccounts.some(a => a.accountNumber === accountNumber)) {
          const slaveAccount = {
            id: Date.now().toString(),
            accountNumber: accountNumber,
            nickname: nickname || '',
            created: new Date().toISOString()
          };

          this.slaveAccounts.unshift(slaveAccount);
          this.saveSlaveAccounts();
          this.renderSlaveAccounts();
          this.updatePairCount();
        }
        
        document.getElementById('slaveAccountNumber').value = '';
        document.getElementById('slaveNickname').value = '';
        
        this.showToast('Slave account added successfully', 'success');
        this.loadData(); // Refresh accounts data
      } else {
        // If account already exists on server, just add to slave list
        if (data.error && data.error.includes('already exists')) {
          if (!this.slaveAccounts.some(a => a.accountNumber === accountNumber)) {
            const slaveAccount = {
              id: Date.now().toString(),
              accountNumber: accountNumber,
              nickname: nickname || '',
              created: new Date().toISOString()
            };

            this.slaveAccounts.unshift(slaveAccount);
            this.saveSlaveAccounts();
            this.renderSlaveAccounts();
            this.updatePairCount();
            
            document.getElementById('slaveAccountNumber').value = '';
            document.getElementById('slaveNickname').value = '';
            
            this.showToast('Account already on server, added as slave account', 'success');
          } else {
            this.showToast('Slave account already exists', 'warning');
          }
        } else {
          this.showToast(data.error || 'Failed to add account', 'error');
        }
      }
    } catch (error) {
      console.error('Failed to add slave account:', error);
      this.showToast('Failed to add slave account', 'error');
    } finally {
      this.hideLoading();
    }
  }

  async addSlaveFromServer() {
    try {
      const response = await fetch('/accounts');
      if (!response.ok) {
        throw new Error('Failed to fetch accounts from server');
      }
      
      const data = await response.json();
      const accounts = data.accounts || [];
      
      if (accounts.length === 0) {
        this.showToast('No accounts found on server', 'warning');
        return;
      }
      
      const existingSlaveNumbers = new Set(this.slaveAccounts.map(a => a.accountNumber));
      const availableAccounts = accounts.filter(acc => !existingSlaveNumbers.has(acc.account));
      
      if (availableAccounts.length === 0) {
        this.showToast('All server accounts are already added as slave accounts', 'info');
        return;
      }
      
      this.showAccountSelectionModal(availableAccounts, 'slave');
      
    } catch (error) {
      console.error('Failed to fetch accounts from server:', error);
      this.showToast('Failed to load accounts from server', 'error');
    }
  }

  loadMasterAccounts() {
    const saved = localStorage.getItem('mt5_master_accounts');
    if (saved) {
      try {
        this.masterAccounts = JSON.parse(saved);
      } catch (e) {
        this.masterAccounts = [];
      }
    }
  }

  saveMasterAccounts() {
    localStorage.setItem('mt5_master_accounts', JSON.stringify(this.masterAccounts));
  }

  loadSlaveAccounts() {
    const saved = localStorage.getItem('mt5_slave_accounts');
    if (saved) {
      try {
        this.slaveAccounts = JSON.parse(saved);
      } catch (e) {
        this.slaveAccounts = [];
      }
    }
  }

  saveSlaveAccounts() {
    localStorage.setItem('mt5_slave_accounts', JSON.stringify(this.slaveAccounts));
  }

  async deleteMasterAccount(accountId) {
  const confirmed = await this.showConfirmDialog(
    'Remove Master Account',
    'Remove this account from Copy Trading page? (Account will remain on the server)'
  );
  if (!confirmed) return;
  this.masterAccounts = this.masterAccounts.filter(a => a.id !== accountId);
  this.saveMasterAccounts();
  this.renderMasterAccounts();
  this.updatePairCount();
  this.showToast('Master account removed from Copy Trading', 'success');
}

  async deleteSlaveAccount(accountId) {
  const confirmed = await this.showConfirmDialog(
    'Remove Slave Account',
    'Remove this account from Copy Trading page? (Account will remain on the server)'
  );
  if (!confirmed) return;
  this.slaveAccounts = this.slaveAccounts.filter(a => a.id !== accountId);
  this.saveSlaveAccounts();
  this.renderSlaveAccounts();
  this.updatePairCount();
  this.showToast('Slave account removed from Copy Trading', 'success');
}

  // Optional: delete Master/Slave account on the server
  async deleteMasterAccountServer(accountId) {
    const ok = await this.showConfirmDialog(
      'Remove Master Account',
      'Remove this account from the server?'
    );
    if (!ok) return;

    try {
      const res = await fetch(`/accounts/${encodeURIComponent(accountId)}`, {
        method: 'DELETE',
        credentials: 'include'
      });
      if (!res.ok) throw new Error(await res.text());
      this.showToast('Master account deleted', 'success');
      // Refresh server-backed tables
      this.loadAccountManagementData?.();
      this.loadData?.();
    } catch (e) {
      console.error(e);
      this.showToast(`Delete failed: ${e.message}`, 'error');
    }
  }

  async deleteSlaveAccountServer(accountId) {
    const ok = await this.showConfirmDialog(
      'Remove Slave Account',
      'Remove this account from the server?'
    );
    if (!ok) return;

    try {
      const res = await fetch(`/accounts/${encodeURIComponent(accountId)}`, {
        method: 'DELETE',
        credentials: 'include'
      });
      if (!res.ok) throw new Error(await res.text());
      this.showToast('Slave account deleted', 'success');
      this.loadAccountManagementData?.();
      this.loadData?.();
    } catch (e) {
      console.error(e);
      this.showToast(`Delete failed: ${e.message}`, 'error');
    }
  }



  renderMasterAccounts() {
  const container = document.getElementById('masterAccountsList');
  if (!container) return;

  if (!this.masterAccounts.length) {
    container.innerHTML = `
      <div class="empty-state-small">
        <i class="fas fa-user"></i>
        <p>No master accounts</p>
      </div>`;
    return;
  }

  container.innerHTML = this.masterAccounts.map(account => {
    // ✅ หาข้อมูลจาก Server Accounts
    const serverAccount = this.accounts.find(a => String(a.account) === String(account.accountNumber));
    
    // ✅ ใช้ Status จาก Server ถ้ามี, ไม่งั้นแสดง Offline
    const status = serverAccount?.status || 'Offline';
    const statusClass = status.toLowerCase();
    
    return `
      <div class="account-card">
        <div class="account-card-info">
          <div class="account-card-number">
            ${this.escape(account.accountNumber)}
            <span class="status-badge ${statusClass}" style="margin-left: 8px; font-size: 0.75rem;">
              <i class="fas fa-circle"></i>
              ${status}
            </span>
          </div>
          <div class="account-card-nickname">${this.escape(account.nickname) || '-'}</div>
        </div>
        <div class="account-card-actions">
          ${status === 'Online' ? `
            <button class="btn btn-warning btn-sm" onclick="ui.performCopyAccountAction('${account.accountNumber}', 'restart')" title="Restart">
              <i class="fas fa-redo"></i>
            </button>
            <button class="btn btn-danger btn-sm" onclick="ui.performCopyAccountAction('${account.accountNumber}', 'stop')" title="Stop">
              <i class="fas fa-stop"></i>
            </button>
          ` : `
            <button class="btn btn-success btn-sm" onclick="ui.performCopyAccountAction('${account.accountNumber}', 'open')" title="Open">
              <i class="fas fa-play"></i>
            </button>
          `}
          <button class="btn btn-secondary btn-sm" onclick="ui.deleteMasterAccount('${account.id}')" title="Delete">
            <i class="fas fa-trash"></i>
          </button>
        </div>
      </div>
    `;
  }).join('');
}

  renderSlaveAccounts() {
  const container = document.getElementById('slaveAccountsList');
  if (!container) return;

  if (!this.slaveAccounts.length) {
    container.innerHTML = `
      <div class="empty-state-small">
        <i class="fas fa-user"></i>
        <p>No slave accounts</p>
      </div>`;
    return;
  }

  container.innerHTML = this.slaveAccounts.map(account => {
    // ✅ หาข้อมูลจาก Server Accounts
    const serverAccount = this.accounts.find(a => String(a.account) === String(account.accountNumber));
    
    // ✅ ใช้ Status จาก Server ถ้ามี, ไม่งั้นแสดง Offline
    const status = serverAccount?.status || 'Offline';
    const statusClass = status.toLowerCase();
    
    return `
      <div class="account-card">
        <div class="account-card-info">
          <div class="account-card-number">
            ${this.escape(account.accountNumber)}
            <span class="status-badge ${statusClass}" style="margin-left: 8px; font-size: 0.75rem;">
              <i class="fas fa-circle"></i>
              ${status}
            </span>
          </div>
          <div class="account-card-nickname">${this.escape(account.nickname) || '-'}</div>
        </div>
        <div class="account-card-actions">
          ${status === 'Online' ? `
            <button class="btn btn-warning btn-sm" onclick="ui.performCopyAccountAction('${account.accountNumber}', 'restart')" title="Restart">
              <i class="fas fa-redo"></i>
            </button>
            <button class="btn btn-danger btn-sm" onclick="ui.performCopyAccountAction('${account.accountNumber}', 'stop')" title="Stop">
              <i class="fas fa-stop"></i>
            </button>
          ` : `
            <button class="btn btn-success btn-sm" onclick="ui.performCopyAccountAction('${account.accountNumber}', 'open')" title="Open">
              <i class="fas fa-play"></i>
            </button>
          `}
          <button class="btn btn-secondary btn-sm" onclick="ui.deleteSlaveAccount('${account.id}')" title="Delete">
            <i class="fas fa-trash"></i>
          </button>
        </div>
      </div>
    `;
  }).join('');
}

  updatePairCount() {
    const badge = document.getElementById('pairCount');
    if (badge) {
      const total = this.masterAccounts.length + this.slaveAccounts.length;
      badge.textContent = `${total} accounts`;
    }
  }

  async toggleCopyPair(pairId, currentStatus) {
    const action = currentStatus === 'active' ? 'stop' : 'start';
    try {
      const res = await fetch(`/api/pairs/${pairId}/${action}`, { method: 'POST' });
      if (res.ok) {
        this.showToast(`Copy pair ${action}ed successfully`, 'success');
        this.loadCopyPairs();
      }
    } catch (e) {
      this.showToast(`Failed to ${action} copy pair`, 'error');
    }
  }

  async deleteCopyPair(pairId) {
    const ok = await this.showConfirmDialog('Delete Copy Pair', 'Are you sure you want to delete this copy trading pair?');
    if (!ok) return;

    try {
      const res = await fetch(`/api/pairs/${pairId}`, { method: 'DELETE' });
      if (res.ok) {
        this.showToast('Copy pair deleted successfully', 'success');
        this.loadCopyPairs();
      }
    } catch (e) {
      this.showToast('Failed to delete copy pair', 'error');
    }
  }

  // New: Delete pair on server + sync UI
  async deletePair(pairId) {
    const ok = await this.showConfirmDialog(
      'Delete Copy Pair',
      'This will permanently remove the pair from the server. Continue?'
    );
    if (!ok) return;

    try {
      const res = await fetch(`/api/pairs/${encodeURIComponent(pairId)}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include'
      });

      if (!res.ok) {
        const t = await res.text();
        throw new Error(`DELETE failed (${res.status}): ${t}`);
      }

      this.showToast('Pair deleted', 'success');
      await this.loadCopyPairs();
    } catch (err) {
      console.error(err);
      this.showToast(`Delete failed: ${err.message}`, 'error');
    }
  }



  renderCopyPairs() {
    const container = document.getElementById('copyPairsList');
    const countBadge = document.getElementById('pairCount');
    
    if (!container) return;
    
    if (countBadge) countBadge.textContent = `${this.copyPairs.length} pairs`;

    if (!this.copyPairs.length) {
      container.innerHTML = `
        <div class="empty-state">
          <i class="fas fa-clipboard-list"></i>
          <p>No Copy Trading Pairs</p>
          <p class="empty-subtitle">Add your first Copy Trading pair above</p>
          <p class="empty-subtitle" style="margin-top:10px;color:var(--warning-color);">
            <i class="fas fa-info-circle"></i> Backend API required for this feature
          </p>
        </div>`;
      return;
    }

    container.innerHTML = this.copyPairs.map(pair => {
      const statusClass = pair.status === 'active' ? 'online' : 'offline';
      const statusText = pair.status === 'active' ? 'Active' : 'Stopped';
      const toggleIcon = pair.status === 'active' ? 'fa-stop' : 'fa-play';
      const toggleText = pair.status === 'active' ? 'Stop' : 'Start';
      const toggleClass = pair.status === 'active' ? 'btn-danger' : 'btn-success';
      
      return `
        <div class="copy-pair-card">
          <div class="pair-header">
            <span class="status-badge ${statusClass}">${statusText}</span>
            <div class="pair-actions">
              <button class="btn ${toggleClass} btn-sm" onclick="ui.toggleCopyPair('${pair.id}', '${pair.status}')">
                <i class="fas ${toggleIcon}"></i> ${toggleText}
              </button>
              <button class="btn btn-secondary btn-sm" onclick="ui.deletePair('${pair.id}')">
                <i class="fas fa-trash"></i>
              </button>
            </div>
          </div>
          <div class="pair-content">
            <div class="account-info">
              <h5><i class="fas fa-user-crown"></i> Master</h5>
              <div class="info-grid">
                <div><strong>Login:</strong> ${this.escape(pair.master.login)}</div>
                <div><strong>Server:</strong> ${this.escape(pair.master.server)}</div>
                <div><strong>Plan:</strong> ${this.escape(pair.master.plan)}</div>
              </div>
            </div>
            <div class="copy-arrow">
              <i class="fas fa-arrow-right"></i>
            </div>
            <div class="account-info">
              <h5><i class="fas fa-user"></i> Slave</h5>
              <div class="info-grid">
                <div><strong>Login:</strong> ${this.escape(pair.slave.login)}</div>
                <div><strong>Server:</strong> ${this.escape(pair.slave.server)}</div>
                <div><strong>Plan:</strong> ${this.escape(pair.slave.plan)}</div>
                <div><strong>Multiplier:</strong> ${pair.volumeMultiplier}x</div>
              </div>
            </div>
          </div>
        </div>`;
    }).join('');
  }

  async loadCopyHistory() {
  try {
    const res = await fetch('/api/copy/history?limit=100');  // เปลี่ยน URL
    if (!res.ok) throw new Error('Failed to load history');
    const data = await res.json();
    this.copyHistory = Array.isArray(data.history) ? data.history : [];
    this.renderCopyHistory();
  } catch (e) {
    console.error('Load history error:', e);
  }
}

  subscribeCopyEvents() {
  try {
    if (this._copyEs) {
      this._copyEs.close();
    }
    const es = new EventSource('/events/copy-trades');
    es.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (data.event === 'copy_history_cleared') {
          this.copyHistory = [];
          this.renderCopyHistory();
          return;
        }
        this.addCopyToHistory(data);
      } catch (e) {
        console.warn('Invalid copy event:', e);
      }
    };
    this._copyEs = es;
  } catch (e) {
    console.warn('Copy SSE unavailable', e);
  }
}

  addCopyToHistory(item) {
    const norm = {
      id: item.id || String(Date.now()),
      status: (item.status || '').toLowerCase() === 'error' ? 'error' : 'success',
      master: item.master || '-',
      slave: item.slave || '-',
      action: item.action || '-',
      symbol: item.symbol || '-',
      volume: item.volume ?? '',
      timestamp: item.timestamp || new Date().toISOString()
    };
    
    this.copyHistory.unshift(norm);
    if (this.copyHistory.length > this.maxCopyHistory) {
      this.copyHistory.pop();
    }
    this.renderCopyHistory();
  }

  renderCopyHistory() {
    const tbody = document.getElementById('copyHistoryTableBody');
    if (!tbody) return;

    const filter = document.getElementById('copyHistoryFilter')?.value || 'all';
    const list = this.copyHistory.filter(item => {
      if (filter === 'success' && item.status !== 'success') return false;
      if (filter === 'error' && item.status !== 'error') return false;
      return true;
    });

    if (!list.length) {
      tbody.innerHTML = `
        <tr class="no-data"><td colspan="7">
          <div class="no-data-message">
            <i class="fas fa-clock-rotate-left"></i>
            <p>No Copy Trading history yet</p>
            <p class="empty-subtitle">History will appear when pairs are active</p>
          </div>
        </td></tr>`;
      return;
    }

    tbody.innerHTML = list.map(item => {
      const badge = item.status === 'success' ? 'online' : 'offline';
      const time = new Date(item.timestamp).toLocaleString();
      return `
        <tr>
          <td><span class="status-badge ${badge}">${item.status}</span></td>
          <td>${this.escape(item.master)}</td>
          <td>${this.escape(item.slave)}</td>
          <td>${this.escape(item.action)}</td>
          <td>${this.escape(item.symbol)}</td>
          <td>${this.escape(item.volume)}</td>
          <td>${this.escape(time)}</td>
        </tr>`;
    }).join('');
  }

  async clearCopyHistory() {
  const ok = await this.showConfirmDialog(
    'Clear Copy History',
    'Delete all copy trading history? This cannot be undone.'
  );
  if (!ok) return;

  try {
    const res = await fetch('/api/copy/history/clear?confirm=1', {
      method: 'POST',
      credentials: 'include'   // ✅ ต้องใส่ เพราะ endpoint ใช้ session
    });

    if (!res.ok) {
      const txt = await res.text();
      throw new Error(`Failed to clear: ${res.status} ${txt}`);
    }

    // ✅ เคลียร์ฝั่ง UI แล้วรีโหลดจากเซิร์ฟเวอร์ให้ชัวร์
    this.copyHistory = [];
    this.renderCopyHistory();
    await this.loadCopyHistory();

    this.showToast('Copy history cleared successfully', 'success');
  } catch (e) {
    console.error(e);
    this.showToast(`Clear failed: ${e.message}`, 'error');
  }
}


  // Plan Management
  loadPlans() {
    const saved = localStorage.getItem('mt5_plans');
    if (saved) {
      try {
        this.plans = JSON.parse(saved);
      } catch (e) {
        this.plans = [];
      }
    }
  }

  savePlans() {
    localStorage.setItem('mt5_plans', JSON.stringify(this.plans));
  }

  addPlan() {
    // Show Create Pair Modal instead
    this.showCreatePairModal();
  }

  showCreatePairModal() {
    // Check if we have master and slave accounts
    if (this.masterAccounts.length === 0) {
      this.showToast('Please add master accounts first', 'warning');
      return;
    }
    
    if (this.slaveAccounts.length === 0) {
      this.showToast('Please add slave accounts first', 'warning');
      return;
    }

    const modalHtml = `
      <div id="createPairModal" class="modal-overlay show">
        <div class="modal" style="max-width: 700px;">
          <div class="modal-header">
            <h4>
              <i class="fas fa-plus-circle"></i> 
              Create Copy Trading Pair
            </h4>
            <button class="modal-close" onclick="ui.closeCreatePairModal()">
              <i class="fas fa-times"></i>
            </button>
          </div>
          <div class="modal-body" style="max-height: 600px; overflow-y: auto;">
            
            <!-- Select Accounts Section -->
            <div class="pair-modal-section">
              <h5 class="pair-modal-section-title">
                <i class="fas fa-circle" style="font-size: 0.5rem; color: var(--primary-color);"></i>
                Select Accounts
              </h5>
              <div class="pair-modal-grid">
                <div class="form-group">
                  <label>Master Account</label>
                  <select id="pairMasterAccount" class="form-input">
                    <option value="">Select master account</option>
                    ${this.masterAccounts.map(acc => `
                      <option value="${this.escape(acc.accountNumber)}">
                        ${this.escape(acc.accountNumber)}${acc.nickname ? ' - ' + this.escape(acc.nickname) : ''}
                      </option>
                    `).join('')}
                  </select>
                </div>
                <div class="form-group">
                  <label>Slave Account</label>
                  <select id="pairSlaveAccount" class="form-input">
                    <option value="">Select slave account</option>
                    ${this.slaveAccounts.map(acc => `
                      <option value="${this.escape(acc.accountNumber)}">
                        ${this.escape(acc.accountNumber)}${acc.nickname ? ' - ' + this.escape(acc.nickname) : ''}
                      </option>
                    `).join('')}
                  </select>
                </div>
              </div>
            </div>

            <!-- Copy Settings Section -->
            <div class="pair-modal-section">
              <h5 class="pair-modal-section-title">
                <i class="fas fa-cog"></i>
                Copy Settings
              </h5>
              
              <div class="pair-modal-settings">
                <div class="pair-modal-setting-item">
                  <div class="pair-modal-setting-info">
                    <div class="pair-modal-setting-label">Auto Mapping Symbol</div>
                    <div class="pair-modal-setting-desc">Automatically map symbols between accounts</div>
                  </div>
                  <label class="toggle-switch">
                    <input type="checkbox" id="pairAutoMapSymbol" checked>
                    <span class="toggle-slider"></span>
                  </label>
                </div>

                <div class="pair-modal-setting-item">
                  <div class="pair-modal-setting-info">
                    <div class="pair-modal-setting-label">Auto Mapping Volume</div>
                    <div class="pair-modal-setting-desc">Automatically adjust volume based on settings</div>
                  </div>
                  <label class="toggle-switch">
                    <input type="checkbox" id="pairAutoMapVolume" checked>
                    <span class="toggle-slider"></span>
                  </label>
                </div>

                <div class="pair-modal-setting-item">
                  <div class="pair-modal-setting-info">
                    <div class="pair-modal-setting-label">Copy TP/SL</div>
                    <div class="pair-modal-setting-desc">Copy take profit and stop loss values</div>
                  </div>
                  <label class="toggle-switch">
                    <input type="checkbox" id="pairCopyPSL" checked>
                    <span class="toggle-slider"></span>
                  </label>
                </div>
              </div>
            </div>

            <!-- Volume Configuration Section -->
            <div class="pair-modal-section">
              <h5 class="pair-modal-section-title">Volume Configuration</h5>
              <div class="pair-modal-grid">
                <div class="form-group">
                  <label>Volume Mode</label>
                  <select id="pairVolumeMode" class="form-input">
                    <option value="multiply">Volume Multiply</option>
                    <option value="fixed">Fixed Volume</option>
                    <option value="percent">Percent of Balance</option>
                  </select>
                </div>
                <div class="form-group">
                  <label>Multiplier</label>
                  <input type="number" id="pairMultiplier" class="form-input" value="2" min="0.01" step="0.01">
                </div>
              </div>
            </div>

            <!-- API Token Section -->
            

          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" onclick="ui.closeCreatePairModal()">
              Cancel
            </button>
            <button class="btn btn-success" onclick="ui.confirmCreatePair()">
              <i class="fas fa-check"></i> Create Pair
            </button>
          </div>
        </div>
      </div>
    `;
    
    const existingModal = document.getElementById('createPairModal');
    if (existingModal) {
      existingModal.remove();
    }
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
  }

  generateApiToken() {
    return 'tk_' + Math.random().toString(36).substr(2, 9) + Date.now().toString(36);
  }

  copyPairToken() {
    const tokenInput = document.getElementById('pairApiToken');
    if (tokenInput) {
      this.copyToClipboard(tokenInput.value, 'API Token copied to clipboard!');
    }
  }

  closeCreatePairModal() {
    const modal = document.getElementById('createPairModal');
    if (modal) {
      modal.remove();
    }
  }

  async confirmCreatePair() {
    const masterAccount = document.getElementById('pairMasterAccount')?.value;
    const slaveAccount  = document.getElementById('pairSlaveAccount')?.value;
    const autoMapSymbol = document.getElementById('pairAutoMapSymbol')?.checked;
    const autoMapVolume = document.getElementById('pairAutoMapVolume')?.checked;
    const copyPSL       = document.getElementById('pairCopyPSL')?.checked;
    const volumeMode    = document.getElementById('pairVolumeMode')?.value || 'multiply';
    const multiplier    = parseFloat(document.getElementById('pairMultiplier')?.value || '2');

    if (!masterAccount) { this.showToast('Please select master account', 'warning'); return; }
    if (!slaveAccount)  { this.showToast('Please select slave account', 'warning');  return; }
    if (masterAccount === slaveAccount) { this.showToast('Master and slave accounts must be different', 'warning'); return; }

    try {
      const res = await fetch('/api/pairs', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          master_account: String(masterAccount),
          slave_account:  String(slaveAccount),
          settings: {
            auto_map_symbol: !!autoMapSymbol,
            auto_map_volume: !!autoMapVolume,
            copy_psl: !!copyPSL,
            volume_mode: volumeMode,
            multiplier: multiplier
          }
        })
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error('Create pair failed: ' + res.status + ' ' + t);
      }
      const resp = await res.json();
      const pair = resp && (resp.pair || resp.data || resp);
      this.showToast('Pair created. API Key: ' + (pair.api_key || pair.apiKey || '(unknown)'), 'success');
      this.closeCreatePairModal();
      await this.loadPlans();
      this.renderPlans();
      if (this.renderActivePairsTable) this.renderActivePairsTable();
    } catch (e) {
      console.error(e);
      this.showToast('Create pair failed', 'error');
    }
  }


  copyPlan(planName) {
    this.copyToClipboard(planName, 'Plan name copied to clipboard!');
  }

  async deletePlan(planId) {
  const confirmed = await this.showConfirmDialog(
    'Delete Copy Trading Pair',
    'Are you sure you want to delete this copy trading pair? This action cannot be undone.'
  );
  if (!confirmed) return;

  try {
    this.showLoading();

    // 🔴 ลบที่เซิร์ฟเวอร์จริง
    const response = await fetch(`/api/pairs/${encodeURIComponent(planId)}`, {
      method: 'DELETE',
      credentials: 'include'
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Failed to delete pair: ${response.status} ${errorText}`);
    }

    // ✅ ลบออกจาก local state (เผื่อ UI เก่า) แล้วรีโหลดจากเซิร์ฟเวอร์เป็นหลัก
    this.plans = this.plans.filter(p => p.id !== planId);
    this.savePlans();

    // ✅ ดึงข้อมูลคู่จากเซิร์ฟเวอร์มาใหม่ (จะอัปเดตทั้ง copyPairs และ plans ให้เอง)
    await this.loadCopyPairs();

    this.showToast('Copy trading pair deleted successfully', 'success');
  } catch (error) {
    console.error('Delete plan error:', error);
    this.showToast(`Failed to delete pair: ${error.message}`, 'error');
  } finally {
    this.hideLoading();
  }
}



  togglePlanStatus(planId) {
  const plan = this.plans.find(p => p.id === planId);
  if (plan) {
    plan.status = plan.status === 'active' ? 'inactive' : 'active';
    this.savePlans();
    
    // ✅ เรียกทั้งสอง Method
    this.renderPlans();
    this.renderActivePairsTable(); // ✅ เพิ่มบรรทัดนี้
    
    this.showToast(`Pair ${plan.status === 'active' ? 'activated' : 'deactivated'}`, 'success');
  }
}


  editPlan(planId) {
    const plan = this.plans.find(p => p.id === planId);
    if (!plan) return;

    // Show edit modal with pre-filled data
    this.showEditPairModal(plan);
  }

  showEditPairModal(plan) {
  const modalHtml = `
    <div id="editPairModal" class="modal-overlay show">
      <div class="modal" style="max-width: 700px;">
        <div class="modal-header">
          <h4>
            <i class="fas fa-edit"></i> 
            Edit Copy Trading Pair
          </h4>
          <button class="modal-close" onclick="ui.closeEditPairModal()">
            <i class="fas fa-times"></i>
          </button>
        </div>
        <div class="modal-body" style="max-height: 600px; overflow-y: auto;">
          
          <!-- Select Accounts Section -->
          <div class="pair-modal-section">
            <h5 class="pair-modal-section-title">
              <i class="fas fa-circle" style="font-size: 0.5rem; color: var(--primary-color);"></i>
              Select Accounts
            </h5>
            <div class="pair-modal-grid">
              <div class="form-group">
                <label>Master Account</label>
                <select id="editPairMasterAccount" class="form-input">
                  <option value="">Select master account</option>
                  ${this.masterAccounts.map(acc => `
                    <option value="${this.escape(acc.accountNumber)}" ${acc.accountNumber === plan.masterAccount ? 'selected' : ''}>
                      ${this.escape(acc.accountNumber)}${acc.nickname ? ' - ' + this.escape(acc.nickname) : ''}
                    </option>
                  `).join('')}
                </select>
              </div>
              <div class="form-group">
                <label>Slave Account</label>
                <select id="editPairSlaveAccount" class="form-input">
                  <option value="">Select slave account</option>
                  ${this.slaveAccounts.map(acc => `
                    <option value="${this.escape(acc.accountNumber)}" ${acc.accountNumber === plan.slaveAccount ? 'selected' : ''}>
                      ${this.escape(acc.accountNumber)}${acc.nickname ? ' - ' + this.escape(acc.nickname) : ''}
                    </option>
                  `).join('')}
                </select>
              </div>
            </div>
          </div>

          <!-- Copy Settings Section -->
          <div class="pair-modal-section">
            <h5 class="pair-modal-section-title">
              <i class="fas fa-cog"></i>
              Copy Settings
            </h5>
            
            <div class="pair-modal-settings">
              <div class="pair-modal-setting-item">
                <div class="pair-modal-setting-info">
                  <div class="pair-modal-setting-label">Auto Mapping Symbol</div>
                  <div class="pair-modal-setting-desc">Automatically map symbols between accounts</div>
                </div>
                <label class="toggle-switch">
                  <input type="checkbox" id="editPairAutoMapSymbol" ${plan.settings.autoMapSymbol ? 'checked' : ''}>
                  <span class="toggle-slider"></span>
                </label>
              </div>

              <div class="pair-modal-setting-item">
                <div class="pair-modal-setting-info">
                  <div class="pair-modal-setting-label">Auto Mapping Volume</div>
                  <div class="pair-modal-setting-desc">Automatically adjust volume based on settings</div>
                </div>
                <label class="toggle-switch">
                  <input type="checkbox" id="editPairAutoMapVolume" ${plan.settings.autoMapVolume ? 'checked' : ''}>
                  <span class="toggle-slider"></span>
                </label>
              </div>

              <div class="pair-modal-setting-item">
                <div class="pair-modal-setting-info">
                  <div class="pair-modal-setting-label">Copy TP/SL</div>
                  <div class="pair-modal-setting-desc">Copy take profit and stop loss values</div>
                </div>
                <label class="toggle-switch">
                  <input type="checkbox" id="editPairCopyPSL" ${plan.settings.copyPSL ? 'checked' : ''}>
                  <span class="toggle-slider"></span>
                </label>
              </div>
            </div>
          </div>

          <!-- Volume Configuration Section -->
          <div class="pair-modal-section">
            <h5 class="pair-modal-section-title">Volume Configuration</h5>
            <div class="pair-modal-grid">
              <div class="form-group">
                <label>Volume Mode</label>
                <select id="editPairVolumeMode" class="form-input">
                  <option value="multiply" ${plan.settings.volumeMode === 'multiply' ? 'selected' : ''}>Volume Multiply</option>
                  <option value="fixed" ${plan.settings.volumeMode === 'fixed' ? 'selected' : ''}>Fixed Volume</option>
                  <option value="percent" ${plan.settings.volumeMode === 'percent' ? 'selected' : ''}>Percent of Balance</option>
                </select>
              </div>
              <div class="form-group">
                <label>Multiplier</label>
                <input type="number" id="editPairMultiplier" class="form-input" value="${plan.settings.multiplier || 2}" min="0.01" step="0.01">
              </div>
            </div>
          </div>

          <!-- API Token Section -->
          <div class="pair-modal-section">
            <h5 class="pair-modal-section-title" style="color: var(--success-color);">
              <i class="fas fa-check-circle"></i>
              API Token
            </h5>
            <div class="form-group">
              <div class="token-input-group">
                <input type="text" id="editPairApiToken" class="form-input" readonly value="${this.escape(plan.apiToken)}" style="font-family: monospace;">
                <button class="btn btn-info btn-sm" onclick="ui.copyToClipboard(document.getElementById('editPairApiToken').value, 'Token copied!')" title="Copy Token">
                  <i class="fas fa-copy"></i>
                </button>
              </div>
            </div>
          </div>

        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" onclick="ui.closeEditPairModal()">
            Cancel
          </button>
          <button class="btn btn-success" onclick="ui.confirmEditPair('${plan.id}')">
            <i class="fas fa-check"></i> Save Changes
          </button>
        </div>
      </div>
    </div>
  `;
  
  const existingModal = document.getElementById('editPairModal');
  if (existingModal) {
    existingModal.remove();
  }
  
  document.body.insertAdjacentHTML('beforeend', modalHtml);
}


  closeEditPairModal() {
    const modal = document.getElementById('editPairModal');
    if (modal) {
      modal.remove();
    }
  }

  confirmEditPair(planId) {
  const masterAccount = document.getElementById('editPairMasterAccount')?.value;
  const slaveAccount = document.getElementById('editPairSlaveAccount')?.value;
  
  // ✅ อ่านค่าจาก Toggle Buttons
  const autoMapSymbol = document.getElementById('editPairAutoMapSymbol')?.checked;
  const autoMapVolume = document.getElementById('editPairAutoMapVolume')?.checked;
  const copyPSL = document.getElementById('editPairCopyPSL')?.checked;
  
  const volumeMode = document.getElementById('editPairVolumeMode')?.value;
  const multiplier = document.getElementById('editPairMultiplier')?.value;

  // Validation
  if (!masterAccount) {
    this.showToast('Please select master account', 'warning');
    return;
  }

  if (!slaveAccount) {
    this.showToast('Please select slave account', 'warning');
    return;
  }

  if (masterAccount === slaveAccount) {
    this.showToast('Master and slave accounts must be different', 'warning');
    return;
  }

  // Find the plan to update
  const planIndex = this.plans.findIndex(p => p.id === planId);
  if (planIndex === -1) {
    this.showToast('Plan not found', 'error');
    return;
  }

  // Get account details
  const masterDetails = this.masterAccounts.find(a => a.accountNumber === masterAccount);
  const slaveDetails = this.slaveAccounts.find(a => a.accountNumber === slaveAccount);

  // ✅ Update the plan with Toggle values
  this.plans[planIndex] = {
    ...this.plans[planIndex],
    masterAccount: masterAccount,
    slaveAccount: slaveAccount,
    masterNickname: masterDetails?.nickname || '',
    slaveNickname: slaveDetails?.nickname || '',
    settings: {
      autoMapSymbol: !!autoMapSymbol,      // ✅ บันทึกค่าใหม่
      autoMapVolume: !!autoMapVolume,      // ✅ บันทึกค่าใหม่
      copyPSL: !!copyPSL,                   // ✅ บันทึกค่าใหม่
      volumeMode: volumeMode || 'multiply',
      multiplier: parseFloat(multiplier) || 2
    }
  };

  this.savePlans();
  this.renderPlans();
  this.renderActivePairsTable();
  this.closeEditPairModal();
  
  this.showToast('Copy trading pair updated successfully!', 'success');
}



  renderPlans() {
    const container = document.getElementById('plansList');
    if (!container) return;

    if (!this.plans.length) {
      container.innerHTML = `
        <div class="empty-state-small">
          <i class="fas fa-layer-group"></i>
          <p>No copy trading pairs yet</p>
          <p style="font-size: 0.85rem; color: var(--text-dim); margin-top: 8px;">
            Create your first pair to start copy trading
          </p>
        </div>`;
      return;
    }

    container.innerHTML = this.plans.map(plan => {
      const statusClass = plan.status === 'active' ? 'online' : 'offline';
      const statusText = plan.status === 'active' ? 'Active' : 'Inactive';
      
      return `
        <div class="plan-item-card">
          <div class="plan-item-header">
            <div class="plan-item-accounts">
              <div class="plan-item-account master">
                <i class="fas fa-user-crown"></i>
                <div class="plan-item-account-info">
                  <div class="plan-item-account-number">${this.escape(plan.masterAccount)}</div>
                  ${plan.masterNickname ? `<div class="plan-item-account-nickname">${this.escape(plan.masterNickname)}</div>` : ''}
                </div>
              </div>
              <div class="plan-item-arrow">
                <i class="fas fa-arrow-right"></i>
              </div>
              <div class="plan-item-account slave">
                <i class="fas fa-user"></i>
                <div class="plan-item-account-info">
                  <div class="plan-item-account-number">${this.escape(plan.slaveAccount)}</div>
                  ${plan.slaveNickname ? `<div class="plan-item-account-nickname">${this.escape(plan.slaveNickname)}</div>` : ''}
                </div>
              </div>
            </div>
            <span class="status-badge ${statusClass}">${statusText}</span>
          </div>
          
          <div class="plan-item-details">
            <div class="plan-item-detail">
              <i class="fas fa-cog"></i>
              <span>${plan.settings.volumeMode || 'multiply'}: ${plan.settings.multiplier}x</span>
            </div>
            <div class="plan-item-detail">
              <i class="fas fa-check-circle" style="color: ${plan.settings.autoMapSymbol ? 'var(--success-color)' : 'var(--text-dim)'}"></i>
              <span>Auto Symbol</span>
            </div>
            <div class="plan-item-detail">
              <i class="fas fa-check-circle" style="color: ${plan.settings.copyPSL ? 'var(--success-color)' : 'var(--text-dim)'}"></i>
              <span>Copy TP/SL</span>
            </div>
          </div>

          <div class="plan-item-token">
            <i class="fas fa-key"></i>
            <code>${this.escape(plan.apiToken)}</code>
            <button class="btn-icon-small" onclick="ui.copyToClipboard('${this.escape(plan.apiToken)}', 'Token copied!')" title="Copy Token">
              <i class="fas fa-copy"></i>
            </button>
          </div>
          
          <div class="plan-item-actions">
            <button class="btn btn-${plan.status === 'active' ? 'warning' : 'success'} btn-sm" onclick="ui.togglePlanStatus('${plan.id}')" title="${plan.status === 'active' ? 'Deactivate' : 'Activate'}">
              <i class="fas fa-${plan.status === 'active' ? 'pause' : 'play'}"></i>
            </button>
            <button class="btn btn-info btn-sm" onclick="ui.editPlan('${plan.id}')" title="Edit">
              <i class="fas fa-edit"></i>
            </button>
            <button class="btn btn-danger btn-sm" onclick="ui.deletePlan('${plan.id}')" title="Delete">
              <i class="fas fa-trash"></i>
            </button>
          </div>
        </div>
      `;
    }).join('');

    // Also update the active pairs table
    this.renderActivePairsTable();
  }

  renderActivePairsTable() {
  const tbody = document.getElementById('activePairsTableBody');
  const countBadge = document.getElementById('activePairsCount');
  
  if (!tbody) return;

  const activePlans = this.plans.filter(p => p.status === 'active');
  
  if (countBadge) {
    countBadge.textContent = `${activePlans.length} active pair${activePlans.length !== 1 ? 's' : ''}`;
  }

  if (!activePlans.length) {
    tbody.innerHTML = `
      <tr class="no-data"><td colspan="7">
        <div class="no-data-message">
          <i class="fas fa-link"></i>
          <p>No active copy trading pairs</p>
          <p class="empty-subtitle">Create and activate a pair above to see it here</p>
        </div>
      </td></tr>`;
    return;
  }

  tbody.innerHTML = activePlans.map(plan => {
    // ✅ หาข้อมูลจาก Server เพื่อแสดงสถานะจริง
    const masterServerAccount = this.accounts.find(a => String(a.account) === String(plan.masterAccount));
    const slaveServerAccount = this.accounts.find(a => String(a.account) === String(plan.slaveAccount));
    
    const masterStatus = masterServerAccount?.status || 'Unknown';
    const slaveStatus = slaveServerAccount?.status || 'Unknown';
    const masterStatusClass = masterStatus.toLowerCase();
    const slaveStatusClass = slaveStatus.toLowerCase();
    
    const masterInfo = `${this.escape(plan.masterAccount)}${plan.masterNickname ? ' (' + this.escape(plan.masterNickname) + ')' : ''}`;
    const slaveInfo = `${this.escape(plan.slaveAccount)}${plan.slaveNickname ? ' (' + this.escape(plan.slaveNickname) + ')' : ''}`;
    
    return `
      <tr>
        <td>
          <div class="pair-table-cell">
            <div class="pair-table-master">
              <i class="fas fa-user-crown" style="color: var(--warning-color);"></i>
              <strong>${masterInfo}</strong>
              <span class="status-badge ${masterStatusClass}" style="margin-left: 8px; font-size: 0.7rem;">
                <i class="fas fa-circle"></i>
                ${masterStatus}
              </span>
            </div>
            <div class="pair-table-arrow">
              <i class="fas fa-arrow-right" style="color: var(--primary-color);"></i>
            </div>
            <div class="pair-table-slave">
              <i class="fas fa-user" style="color: var(--info-color);"></i>
              <strong>${slaveInfo}</strong>
              <span class="status-badge ${slaveStatusClass}" style="margin-left: 8px; font-size: 0.7rem;">
                <i class="fas fa-circle"></i>
                ${slaveStatus}
              </span>
            </div>
          </div>
        </td>
        <td>
          <div class="pair-table-toggle">
            <label class="toggle-switch-small">
              <input type="checkbox" ${plan.settings.autoMapSymbol ? 'checked' : ''} disabled>
              <span class="toggle-slider-small"></span>
            </label>
            <span class="toggle-label">${plan.settings.autoMapSymbol ? 'ON' : 'OFF'}</span>
          </div>
        </td>
        <td>
          <div class="pair-table-toggle">
            <label class="toggle-switch-small">
              <input type="checkbox" ${plan.settings.autoMapVolume ? 'checked' : ''} disabled>
              <span class="toggle-slider-small"></span>
            </label>
            <span class="toggle-label">${plan.settings.autoMapVolume ? 'ON' : 'OFF'}</span>
          </div>
        </td>
        <td>
          <div class="pair-table-toggle">
            <label class="toggle-switch-small">
              <input type="checkbox" ${plan.settings.copyPSL ? 'checked' : ''} disabled>
              <span class="toggle-slider-small"></span>
            </label>
            <span class="toggle-label">${plan.settings.copyPSL ? 'ON' : 'OFF'}</span>
          </div>
        </td>
        <td>
          <span class="volume-mode-badge">
            ${this.escape(plan.settings.volumeMode || 'multiply')} ×${plan.settings.multiplier}
          </span>
        </td>
        <td>
          <div class="api-token-cell">
            <code>${this.escape(plan.apiToken)}</code>
            <button class="btn-icon-small" onclick="ui.copyToClipboard('${this.escape(plan.apiToken)}', 'Token copied!')" title="Copy Token">
              <i class="fas fa-copy"></i>
            </button>
          </div>
        </td>
        <td>
          <div class="action-buttons">
            <button class="btn btn-info btn-sm" onclick="ui.editPlan('${plan.id}')" title="Settings">
              <i class="fas fa-cog"></i>
            </button>
            <button class="btn btn-danger btn-sm" onclick="ui.togglePlanStatus('${plan.id}')" title="Deactivate">
              <i class="fas fa-power-off"></i>
            </button>
          </div>
        </td>
      </tr>`;
  }).join('');
}


  togglePassword(inputId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    
    const btn = input.parentElement.querySelector('.password-toggle');
    if (input.type === 'password') {
      input.type = 'text';
      if (btn) btn.innerHTML = '<i class="fas fa-eye-slash"></i>';
    } else {
      input.type = 'password';
      if (btn) btn.innerHTML = '<i class="fas fa-eye"></i>';
    }
  }

  showExample(index) {
    this.currentExampleIndex = index;
    const example = this.jsonExamples[index];
    document.querySelectorAll('.example-nav-btn').forEach((btn, i) => {
      btn.classList.toggle('active', i === index);
    });
    const titleEl = document.getElementById('exampleTitle');
    const codeEl = document.getElementById('jsonCode');
    if (titleEl) titleEl.textContent = example.title;
    if (codeEl) codeEl.textContent = example.json;
  }

  copyExample() {
    const jsonCode = document.getElementById('jsonCode');
    if (jsonCode) {
      this.copyToClipboard(jsonCode.textContent, 'JSON example copied to clipboard!');
    }
  }

  async copyWebhookUrl() {
    if (!this.webhookUrl) {
      this.showToast('Webhook URL not available', 'warning');
      return;
    }
    this.copyToClipboard(this.webhookUrl, 'Webhook URL copied to clipboard!');
  }
async copyCopyTradingEndpoint() {
  try {
    let baseUrl = '';
    if (this.webhookUrl) {
      const url = new URL(this.webhookUrl);
      baseUrl = `${url.protocol}//${url.host}`;
    } else {
      baseUrl = `${window.location.protocol}//${window.location.host}`;
    }
    const copyTradingEndpoint = `${baseUrl}/api/copy/trade`;
    await this.copyToClipboard(copyTradingEndpoint, 'Copy Trading Endpoint copied to clipboard!');
  } catch (error) {
    console.error('Failed to copy endpoint:', error);
    this.showToast('Failed to copy endpoint', 'error');
  }
}


  copyToClipboard(text, successMsg = 'Copied to clipboard!') {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(() => {
        this.showToast?.(successMsg, 'success');
      }).catch(err => {
        throw err;
      });
    } else {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(ta);
      if (!ok) throw new Error('execCommand copy failed');
      this.showToast?.(successMsg, 'success');
    }
  } catch (err) {
    console.error('Clipboard copy failed:', err);
    this.showToast?.('Failed to copy to clipboard', 'error');
  }
}

  showAccountSelectionModalForWebhook(accounts) {
    const modalHtml = `
      <div id="webhookAccountSelectionModal" class="modal-overlay show">
        <div class="modal" style="max-width: 600px;">
          <div class="modal-header">
            <h4>
              <i class="fas fa-server"></i> 
              Select Accounts from Server
            </h4>
            <button class="modal-close" onclick="ui.closeWebhookAccountSelectionModal()">
              <i class="fas fa-times"></i>
            </button>
          </div>
          <div class="modal-body" style="max-height: 500px; overflow-y: auto;">
            <p style="margin-bottom: 16px; color: var(--text-dim);">
              Select accounts to add to the webhook page:
            </p>
            <div id="webhookAccountSelectionList" class="account-selection-list">
              ${accounts.map(acc => `
                <div class="account-selection-item" data-account="${this.escape(acc.account)}">
                  <label class="account-selection-label">
                    <input 
                      type="checkbox" 
                      class="webhook-account-checkbox" 
                      value="${this.escape(acc.account)}"
                      data-nickname="${this.escape(acc.nickname || '')}"
                      data-status="${this.escape(acc.status || '')}"
                      data-pid="${this.escape(acc.pid || '')}"
                      data-created="${this.escape(acc.created || '')}"
                    />
                    <div class="account-selection-info">
                      <div class="account-selection-number">
                        <i class="fas fa-user"></i>
                        ${this.escape(acc.account)}
                      </div>
                      <div class="account-selection-details">
                        <span class="status-badge ${(acc.status || '').toLowerCase()}">
                          ${this.escape(acc.status || 'Unknown')}
                        </span>
                        ${acc.nickname ? `<span class="account-selection-nickname">${this.escape(acc.nickname)}</span>` : ''}
                      </div>
                    </div>
                  </label>
                </div>
              `).join('')}
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" onclick="ui.closeWebhookAccountSelectionModal()">
              Cancel
            </button>
            <button class="btn btn-success" onclick="ui.confirmWebhookAccountSelection()">
              <i class="fas fa-check"></i> Add Selected Accounts
            </button>
          </div>
        </div>
      </div>
    `;
    
    const existingModal = document.getElementById('webhookAccountSelectionModal');
    if (existingModal) {
      existingModal.remove();
    }
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
  }

  closeWebhookAccountSelectionModal() {
    const modal = document.getElementById('webhookAccountSelectionModal');
    if (modal) {
      modal.remove();
    }
  }

  confirmWebhookAccountSelection() {
    const checkboxes = document.querySelectorAll('.webhook-account-checkbox:checked');
    if (checkboxes.length === 0) {
      this.showToast('Please select at least one account', 'warning');
      return;
    }
    let addedCount = 0;
    const newlyAdded = [];

    checkboxes.forEach(checkbox => {
      const accountNumber = checkbox.value;
      const nickname = checkbox.dataset.nickname || '';
      const status = checkbox.dataset.status || 'Offline';
      const pid = checkbox.dataset.pid || '';
      const created = checkbox.dataset.created || new Date().toISOString();

      if (!this.webhookAccounts.some(a => (a.account || a.id) === accountNumber)) {
        const obj = { account: accountNumber, nickname, status, pid, created, enabled: true };
        this.webhookAccounts.push(obj);
        newlyAdded.push(obj);
        addedCount++;
      }
    });

    // Persist to server if endpoint exists; otherwise fallback to localStorage
    const persist = async () => {
      try {
        const res = await fetch('/webhook-accounts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(newlyAdded[0] || {})
        });
        if (!res.ok) throw new Error('endpoint not ready');
        for (let i = 1; i < newlyAdded.length; i++) {
          await fetch('/webhook-accounts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newlyAdded[i])
          });
        }
      } catch (e) {
        localStorage.setItem('mt5_webhook_accounts', JSON.stringify(this.webhookAccounts));
      }
    };

    if (addedCount > 0) {
      persist().finally(() => {
        this.updateAccountsTable();
        this.updateStats();
        this.showToast(`Successfully added ${addedCount} account(s) to webhook page`, 'success');
        this.closeWebhookAccountSelectionModal();
      });
    } else {
      this.showToast('Selected accounts already exist on this page', 'warning');
      this.closeWebhookAccountSelectionModal();
    }
  }

  showAccountSelectionModal(accounts, type) {
    const modalHtml = `
      <div id="accountSelectionModal" class="modal-overlay show">
        <div class="modal" style="max-width: 600px;">
          <div class="modal-header">
            <h4>
              <i class="fas fa-server"></i> 
              Select ${type === 'master' ? 'Master' : 'Slave'} Account from Server
            </h4>
            <button class="modal-close" onclick="ui.closeAccountSelectionModal()">
              <i class="fas fa-times"></i>
            </button>
          </div>
          <div class="modal-body" style="max-height: 500px; overflow-y: auto;">
            <p style="margin-bottom: 16px; color: var(--text-dim);">
              Select accounts to add as ${type === 'master' ? 'master' : 'slave'} accounts:
            </p>
            <div id="accountSelectionList" class="account-selection-list">
              ${accounts.map(acc => `
                <div class="account-selection-item" data-account="${this.escape(acc.account)}">
                  <label class="account-selection-label">
                    <input 
                      type="checkbox" 
                      class="account-checkbox" 
                      value="${this.escape(acc.account)}"
                      data-nickname="${this.escape(acc.nickname || '')}"
                    />
                    <div class="account-selection-info">
                      <div class="account-selection-number">
                        <i class="fas fa-user"></i>
                        ${this.escape(acc.account)}
                      </div>
                      <div class="account-selection-details">
                        <span class="status-badge ${(acc.status || '').toLowerCase()}">
                          ${this.escape(acc.status || 'Unknown')}
                        </span>
                        ${acc.nickname ? `<span class="account-selection-nickname">${this.escape(acc.nickname)}</span>` : ''}
                      </div>
                    </div>
                  </label>
                </div>
              `).join('')}
            </div>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" onclick="ui.closeAccountSelectionModal()">
              Cancel
            </button>
            <button class="btn btn-success" onclick="ui.confirmAccountSelection('${type}')">
              <i class="fas fa-check"></i> Add Selected Accounts
            </button>
          </div>
        </div>
      </div>
    `;
    
    const existingModal = document.getElementById('accountSelectionModal');
    if (existingModal) {
      existingModal.remove();
    }
    
    document.body.insertAdjacentHTML('beforeend', modalHtml);
  }

  closeAccountSelectionModal() {
    const modal = document.getElementById('accountSelectionModal');
    if (modal) {
      modal.remove();
    }
  }

  confirmAccountSelection(type) {
    const checkboxes = document.querySelectorAll('.account-checkbox:checked');
    
    if (checkboxes.length === 0) {
      this.showToast('Please select at least one account', 'warning');
      return;
    }
    
    let addedCount = 0;
    let skippedCount = 0;
    
    checkboxes.forEach(checkbox => {
      const accountNumber = checkbox.value;
      const nickname = checkbox.dataset.nickname || '';
      
      if (type === 'master') {
        if (this.masterAccounts.some(a => a.accountNumber === accountNumber)) {
          skippedCount++;
          return;
        }
        
        const masterAccount = {
          id: Date.now().toString() + '_' + Math.random().toString(36).substr(2, 9),
          accountNumber: accountNumber,
          nickname: nickname,
          created: new Date().toISOString()
        };
        
        this.masterAccounts.unshift(masterAccount);
        addedCount++;
      } else {
        if (this.slaveAccounts.some(a => a.accountNumber === accountNumber)) {
          skippedCount++;
          return;
        }
        
        const slaveAccount = {
          id: Date.now().toString() + '_' + Math.random().toString(36).substr(2, 9),
          accountNumber: accountNumber,
          nickname: nickname,
          created: new Date().toISOString()
        };
        
        this.slaveAccounts.unshift(slaveAccount);
        addedCount++;
      }
    });
    
    if (type === 'master') {
      this.saveMasterAccounts();
      this.renderMasterAccounts();
    } else {
      this.saveSlaveAccounts();
      this.renderSlaveAccounts();
    }
    
    this.updatePairCount();
    this.closeAccountSelectionModal();
    
    if (addedCount > 0 && skippedCount > 0) {
      this.showToast(`Added ${addedCount} account(s), ${skippedCount} skipped (already exist)`, 'success');
    } else if (addedCount > 0) {
      this.showToast(`Successfully added ${addedCount} ${type} account(s)`, 'success');
    } else {
      this.showToast('All selected accounts already exist', 'warning');
    }
  }


  showToast(message, type = 'info', duration = 5000) {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    
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
      <div class="toast-icon"><i class="fas fa-${icons[type]}"></i></div>
      <div class="toast-content">
        <div class="toast-title">${titles[type]}</div>
        <div class="toast-message">${message}</div>
      </div>
      <button class="toast-close" onclick="this.parentElement.remove()"><i class="fas fa-times"></i></button>`;
    
    container.appendChild(toast);
    setTimeout(() => {
      if (toast.parentElement) toast.remove();
    }, duration);
  }

  showConfirmDialog(title, message) {
    return new Promise((resolve) => {
      const modal = document.getElementById('modalOverlay');
      if (!modal) {
        resolve(false);
        return;
      }
      
      const titleEl = document.getElementById('modalTitle');
      const messageEl = document.getElementById('modalMessage');
      if (titleEl) titleEl.textContent = title;
      if (messageEl) messageEl.textContent = message;
      
      modal.classList.add('show');
      
      const confirmBtn = document.getElementById('modalConfirmBtn');
      const handler = () => {
        resolve(true);
        cleanup();
      };
      const cleanup = () => {
        if (confirmBtn) confirmBtn.removeEventListener('click', handler);
        this.closeModal();
      };
      
      if (confirmBtn) {
        confirmBtn.addEventListener('click', handler, { once: true });
      }
      
      this.currentAction = (ok) => {
        resolve(!!ok);
        cleanup();
      };
    });
  }

  closeModal() {
    const modal = document.getElementById('modalOverlay');
    if (modal) modal.classList.remove('show');
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
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) overlay.classList.add('show');
  }

  hideLoading() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) overlay.classList.remove('show');
  }

  startAutoRefresh() {
    this.refreshInterval = setInterval(() => {
      if (!document.hidden) {
        this.loadData();
        if (this.currentPage === 'copytrading') {
          this.loadCopyPairs();
        }
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
    if (isNaN(date)) return '-';
    const now = new Date();
    const diff = now - date;
    const day = 1000 * 60 * 60 * 24;
    const d = Math.floor(diff / day);
    if (d === 0) return 'Today ' + date.toLocaleTimeString();
    if (d === 1) return 'Yesterday ' + date.toLocaleTimeString();
    if (d < 7) return `${d} days ago`;
    return date.toLocaleDateString();
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
      if (this._es) {
        try { this._es.close(); } catch {}
      }
      const es = new EventSource('/events/trades');
      es.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data);

          if (data.event === 'history_cleared') {
            this.tradeHistory = [];
            this.renderHistory();
            this.updateAccountFilterOptions();
            return;
          }

          if (data.event === 'account_deleted' && data.account) {
            this.tradeHistory = this.tradeHistory.filter(t =>
              String(t.account) !== String(data.account)
            );
            this.renderHistory();
            this.updateAccountFilterOptions();
            return;
          }

          this.addTradeToHistory(data);
        } catch (e) {
          console.warn('Invalid trade event:', e);
        }
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
    this.updateAccountFilterOptions();
    this.renderHistory();
  }

  updateAccountFilterOptions() {
    const sel = document.getElementById('accountFilter');
    if (!sel) return;

    const current = sel.value || 'all';
    const fromHistory = (this.tradeHistory || [])
      .map(t => String(t.account || '').trim())
      .filter(Boolean);
    const fromWebhook = (this.webhookAccounts || []).map(a => String(a.account || a.id || '').trim()).filter(Boolean);
    const all = Array.from(new Set([...fromHistory, ...fromWebhook])).sort((a, b) => a.localeCompare(b));

    const html = ['<option value="all">All Accounts</option>']
      .concat(all.map(acc => `<option value="${this.escape(acc)}">${this.escape(acc)}</option>`))
      .join('');
    sel.innerHTML = html;

    if ([...sel.options].some(o => o.value === current)) sel.value = current;
    else sel.value = 'all';
  }

  renderHistory() {
    const tbody = document.getElementById('historyTableBody');
    if (!tbody) return;

    const statusSel = document.getElementById('historyFilter');
    const statusFilter = (statusSel?.value || 'all').toLowerCase();

    const accSel = document.getElementById('accountFilter');
    const accountFilter = (accSel?.value || 'all').toLowerCase();

    const list = this.tradeHistory.filter(t => {
      if (statusFilter === 'success' && t.status !== 'success') return false;
      if (statusFilter === 'error' && t.status !== 'error') return false;
      if (accountFilter !== 'all' && String(t.account).toLowerCase() !== accountFilter) return false;
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
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;'
    }[s]));
  }

  async clearHistory() {
    const ok = await this.showConfirmDialog('Clear Trading History', 'Delete all saved trade history? This cannot be undone.');
    if (!ok) return;

    try {
      const res = await fetch('/trades/clear?confirm=1', { method: 'POST' });
      const serverCleared = res.ok;

      if (serverCleared) {
        this.tradeHistory = [];
        this.renderHistory();
        this.updateAccountFilterOptions();
        this.showToast('History cleared successfully', 'success');
      } else {
        this.showToast('Failed to clear history', 'error');
      }
    } catch (e) {
      console.error('Clear history error:', e);
      this.showToast('Failed to clear history', 'error');
    }
  }

  cleanup() {
    this.stopAutoRefresh();
    if (this._es) {
      try { this._es.close(); } catch {}
    }
    if (this._copyEs) {
      try { this._copyEs.close(); } catch {}
    }
  }
}

// Helper functions
function showExample(i) {
  if (window.ui) window.ui.showExample(i);
}

function copyExample() {
  if (window.ui) window.ui.copyExample();
}

function copyWebhookUrl() {
  if (window.ui) window.ui.copyWebhookUrl();
}

function closeModal() {
  if (window.ui) window.ui.closeModal();
}

function confirmAction() {
  if (window.ui) window.ui.confirmAction();
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  window.ui = new TradingBotUI();
});

window.addEventListener('beforeunload', () => {
  if (window.ui) window.ui.cleanup();
});

// END OF APP.JS
