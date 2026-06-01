// ─────────────────────────────────────────────────────────────────────────────
// Agent Monitoring Dashboard - JavaScript
// ─────────────────────────────────────────────────────────────────────────────

const API_BASE = '';  // Same origin

// DOM elements
const autoRefreshToggle = document.getElementById('auto-refresh-toggle');
const lastUpdateEl = document.getElementById('last-update');
const sessionsTbody = document.getElementById('sessions-tbody');
const sessionCountEl = document.getElementById('session-count');
const logCountEl = document.getElementById('log-count');
const modalOverlay = document.getElementById('modal-overlay');
const modalBody = document.getElementById('modal-body');

// State
let autoRefreshInterval = null;
let allReports = [];

// ─────────────────────────────────────────────────────────────────────────────
// Data fetching
// ─────────────────────────────────────────────────────────────────────────────

async function fetchJSON(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}

async function refreshAll() {
    try {
        const [historical, tools, logs] = await Promise.all([
            fetchJSON(`${API_BASE}/api/monitoring/historical`),
            fetchJSON(`${API_BASE}/api/monitoring/tools`),
            fetchJSON(`${API_BASE}/api/monitoring/logs?limit=50`),
        ]);

        renderStats(historical);
        renderSessions(historical.sessions || []);
        renderToolUsage(tools.tool_usage || {});
        renderLogs(logs.logs || []);

        lastUpdateEl.textContent = new Date().toLocaleTimeString('vi-VN');
    } catch (err) {
        console.error('Refresh failed:', err);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Render: Stats cards
// ─────────────────────────────────────────────────────────────────────────────

function renderStats(data) {
    setText('stat-sessions', data.total_sessions || 0);
    setText('stat-cost', `$${(data.total_cost || 0).toFixed(4)}`);
    setText('stat-tokens', formatNumber(data.total_tokens || 0));
    setText('stat-latency', `${data.avg_latency_ms || 0}ms`);
    setText('stat-tps', data.avg_tokens_per_second || 0);
    setText('stat-success', `${data.success_rate || 0}%`);
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function formatNumber(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
    if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
    return n.toString();
}

// ─────────────────────────────────────────────────────────────────────────────
// Render: Sessions table
// ─────────────────────────────────────────────────────────────────────────────

function renderSessions(sessions) {
    allReports = sessions;
    sessionCountEl.textContent = sessions.length;

    if (sessions.length === 0) {
        sessionsTbody.innerHTML = `
            <tr><td colspan="8" class="empty-state">No sessions recorded yet</td></tr>
        `;
        return;
    }

    sessionsTbody.innerHTML = sessions.map((s, i) => {
        const summary = s.summary || {};
        const statusClass = s.status === 'final_answer' ? 'success'
            : s.status === 'llm_error' ? 'error' : 'warning';
        const statusLabel = s.status === 'final_answer' ? 'Success'
            : s.status === 'llm_error' ? 'Error' : s.status;

        return `
            <tr>
                <td class="mono">${formatTime(s.timestamp)}</td>
                <td title="${escapeHtml(s.user_input)}">${escapeHtml(s.user_input)}</td>
                <td><span class="status-badge ${statusClass}">${statusLabel}</span></td>
                <td class="mono">${formatNumber(summary.total_tokens || 0)}</td>
                <td class="mono">${summary.total_latency_ms || 0}ms</td>
                <td class="mono">$${(summary.total_cost_estimate || 0).toFixed(6)}</td>
                <td class="mono">${summary.avg_tokens_per_second || 0}</td>
                <td><button class="btn-detail" onclick="showDetail(${i})">Detail</button></td>
            </tr>
        `;
    }).join('');
}

function formatTime(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleString('vi-VN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        day: '2-digit',
        month: '2-digit',
    });
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// ─────────────────────────────────────────────────────────────────────────────
// Render: Tool usage
// ─────────────────────────────────────────────────────────────────────────────

function renderToolUsage(toolUsage) {
    const container = document.getElementById('tool-usage-chart');
    const entries = Object.entries(toolUsage);

    if (entries.length === 0) {
        container.innerHTML = '<div class="empty-state">No tool data yet</div>';
        return;
    }

    const max = Math.max(...entries.map(([, v]) => v));

    container.innerHTML = entries.map(([name, count]) => {
        const pct = max > 0 ? (count / max) * 100 : 0;
        return `
            <div class="tool-bar-row">
                <span class="tool-bar-label">${escapeHtml(name)}</span>
                <div class="tool-bar-track">
                    <div class="tool-bar-fill" style="width: ${pct}%"></div>
                </div>
                <span class="tool-bar-count">${count}</span>
            </div>
        `;
    }).join('');
}

// ─────────────────────────────────────────────────────────────────────────────
// Render: Logs
// ─────────────────────────────────────────────────────────────────────────────

function renderLogs(logs) {
    const container = document.getElementById('logs-container');
    logCountEl.textContent = logs.length;

    if (logs.length === 0) {
        container.innerHTML = '<div class="empty-state">No logs yet</div>';
        return;
    }

    // Show last 30 logs in reverse order
    const recent = logs.slice(-30).reverse();

    container.innerHTML = recent.map(entry => {
        const event = entry.event || '';
        const eventClass = getEventClass(event);
        const time = entry.timestamp ? new Date(entry.timestamp).toLocaleTimeString('vi-VN') : '';
        const data = entry.data ? truncate(JSON.stringify(entry.data), 120) : '';

        return `
            <div class="log-entry ${eventClass === 'error' ? 'error' : ''}">
                <span class="log-time">${time}</span>
                <span class="log-event ${eventClass}">${event}</span>
                <span class="log-data">${escapeHtml(data)}</span>
            </div>
        `;
    }).join('');
}

function getEventClass(event) {
    if (event.includes('ERROR') || event.includes('FAILED')) return 'error';
    if (event.includes('LLM')) return 'llm';
    if (event.includes('TOOL')) return 'tool';
    if (event.includes('SESSION') || event.includes('REPORT')) return 'session';
    if (event.includes('AGENT_START')) return 'agent';
    return '';
}

function truncate(str, max) {
    return str.length > max ? str.slice(0, max) + '...' : str;
}

// ─────────────────────────────────────────────────────────────────────────────
// Modal: Report detail
// ─────────────────────────────────────────────────────────────────────────────

async function showDetail(index) {
    const report = allReports[index];
    if (!report) return;

    try {
        const detail = await fetchJSON(`${API_BASE}/api/monitoring/reports/${report.filename}`);
        renderModal(detail);
        modalOverlay.classList.add('active');
    } catch (err) {
        console.error('Failed to load report detail:', err);
    }
}

function renderModal(data) {
    const summary = data.summary || {};
    const details = data.details || [];

    let html = `
        <div class="detail-grid">
            <div class="detail-item">
                <div class="detail-label">Status</div>
                <div class="detail-value">${data.status || 'N/A'}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">Total Tokens</div>
                <div class="detail-value">${formatNumber(summary.total_tokens || 0)}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">Total Latency</div>
                <div class="detail-value">${summary.total_latency_ms || 0}ms</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">Total Cost</div>
                <div class="detail-value">$${(summary.total_cost_estimate || 0).toFixed(6)}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">Tokens/sec</div>
                <div class="detail-value">${summary.avg_tokens_per_second || 0}</div>
            </div>
            <div class="detail-item">
                <div class="detail-label">Token Ratio</div>
                <div class="detail-value">${summary.token_ratio || 0}</div>
            </div>
        </div>

        <div class="detail-item" style="margin-bottom: 20px;">
            <div class="detail-label">User Input</div>
            <div class="detail-value" style="font-size: 14px; font-family: Inter, sans-serif;">
                ${escapeHtml(data.user_input || '')}
            </div>
        </div>

        <div class="detail-item" style="margin-bottom: 20px;">
            <div class="detail-label">Final Answer</div>
            <div class="detail-value" style="font-size: 14px; font-family: Inter, sans-serif;">
                ${escapeHtml(data.final_answer || '')}
            </div>
        </div>
    `;

    if (details.length > 0) {
        html += `
            <div class="detail-section">
                <h3>LLM Request Details</h3>
                <table class="detail-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Provider</th>
                            <th>Prompt Tokens</th>
                            <th>Completion</th>
                            <th>Latency</th>
                            <th>Cost</th>
                            <th>TPS</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${details.map((d, i) => `
                            <tr>
                                <td>${i + 1}</td>
                                <td>${d.provider || ''}</td>
                                <td>${d.prompt_tokens || 0}</td>
                                <td>${d.completion_tokens || 0}</td>
                                <td>${d.latency_ms || 0}ms</td>
                                <td>$${(d.cost_estimate || 0).toFixed(6)}</td>
                                <td>${d.tokens_per_second || 0}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    }

    // Tool usage
    const toolUsage = summary.tool_usage || {};
    if (Object.keys(toolUsage).length > 0) {
        html += `
            <div class="detail-section">
                <h3>Tool Usage</h3>
                <div class="detail-grid">
                    ${Object.entries(toolUsage).map(([name, count]) => `
                        <div class="detail-item">
                            <div class="detail-label">${escapeHtml(name)}</div>
                            <div class="detail-value">${count} calls</div>
                        </div>
                    `).join('')}
                </div>
            </div>
        `;
    }

    modalBody.innerHTML = html;
}

function closeModal() {
    modalOverlay.classList.remove('active');
}

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeModal();
});

// ─────────────────────────────────────────────────────────────────────────────
// Auto-refresh
// ─────────────────────────────────────────────────────────────────────────────

function startAutoRefresh() {
    stopAutoRefresh();
    autoRefreshInterval = setInterval(refreshAll, 10000);
}

function stopAutoRefresh() {
    if (autoRefreshInterval) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = null;
    }
}

autoRefreshToggle.addEventListener('change', () => {
    if (autoRefreshToggle.checked) {
        startAutoRefresh();
    } else {
        stopAutoRefresh();
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// Init
// ─────────────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
    await refreshAll();
    startAutoRefresh();
});
