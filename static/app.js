// ─────────────────────────────────────────────────────────────────────────────
// DOM Elements
// ─────────────────────────────────────────────────────────────────────────────
const chatHistory   = document.getElementById('chat-history');
const chatForm      = document.getElementById('chat-form');
const chatInput     = document.getElementById('chat-input');
const btnSubmit     = document.getElementById('btn-submit');
const chatSuggestions = document.getElementById('chat-suggestions');

// Sidebar elements
const sidebar         = document.getElementById('sidebar');
const sidebarSessions = document.getElementById('sidebar-sessions');
const sessionsEmpty   = document.getElementById('sessions-empty');
const sidebarOverlay  = document.getElementById('sidebar-overlay');
const btnNewChat      = document.getElementById('btn-new-chat');
const sessionTitle    = document.getElementById('session-title-display');
const btnRename       = document.getElementById('btn-rename-session');
const sidebarOpenBtn  = document.getElementById('sidebar-open-btn');
const sidebarCloseBtn = document.getElementById('sidebar-close-btn');

// Context menu
const contextMenu = document.getElementById('session-context-menu');
const ctxRename   = document.getElementById('ctx-rename');
const ctxDelete   = document.getElementById('ctx-delete');

// ─────────────────────────────────────────────────────────────────────────────
// State
// ─────────────────────────────────────────────────────────────────────────────
let isProcessing    = false;
let currentSessionId = null;   // active session
let sessions        = [];      // cached session list
let ctxTargetId     = null;    // session id for context menu

// ─────────────────────────────────────────────────────────────────────────────
// Sidebar open / close
// ─────────────────────────────────────────────────────────────────────────────
const MOBILE_BREAKPOINT = 900;

function isMobile() {
    return window.innerWidth <= MOBILE_BREAKPOINT;
}

function openSidebar() {
    sidebar.classList.remove('collapsed');
    // Only show overlay on mobile — on desktop sidebar sits side-by-side
    if (isMobile()) {
        sidebarOverlay.classList.add('visible');
    }
}

function closeSidebar() {
    sidebar.classList.add('collapsed');
    sidebarOverlay.classList.remove('visible');
}

function toggleSidebar() {
    if (sidebar.classList.contains('collapsed')) {
        openSidebar();
    } else {
        closeSidebar();
    }
}

// On resize: if switching from mobile → desktop, remove overlay & ensure sidebar is open
window.addEventListener('resize', () => {
    if (!isMobile()) {
        sidebarOverlay.classList.remove('visible');
        // Restore sidebar on desktop if it was collapsed
        if (sidebar.classList.contains('collapsed')) {
            sidebar.classList.remove('collapsed');
        }
    }
});

if (sidebarOpenBtn)  sidebarOpenBtn.addEventListener('click', toggleSidebar);
if (sidebarCloseBtn) sidebarCloseBtn.addEventListener('click', toggleSidebar);

// ─────────────────────────────────────────────────────────────────────────────
// Session management
// ─────────────────────────────────────────────────────────────────────────────

/** Fetch all sessions from API and re-render the sidebar list */
async function loadSessions() {
    try {
        const res = await fetch('/api/sessions');
        if (!res.ok) return;
        const data = await res.json();
        sessions = data.sessions || [];
        renderSessionList();
    } catch (err) {
        console.error('Failed to load sessions:', err);
    }
}

/** Render the sidebar session list from the cached `sessions` array */
function renderSessionList() {
    sidebarSessions.innerHTML = '';

    if (sessions.length === 0) {
        sessionsEmpty.style.display = 'flex';
        sidebarSessions.appendChild(sessionsEmpty);
        return;
    }

    sessionsEmpty.style.display = 'none';

    sessions.forEach(session => {
        const item = document.createElement('div');
        item.classList.add('session-item');
        item.dataset.id = session.id;
        if (session.id === currentSessionId) item.classList.add('active');

        const timeLabel = formatRelativeTime(session.updated_at);

        item.innerHTML = `
            <div class="session-item-icon">
                <i class="fa-regular fa-comment-dots"></i>
            </div>
            <div class="session-item-text">
                <div class="session-item-title" title="${escapeHtml(session.title)}">${escapeHtml(session.title)}</div>
                <div class="session-item-time">${timeLabel}</div>
            </div>
            <div class="session-item-actions">
                <button class="session-action-btn" title="Đổi tên" data-action="rename" data-id="${session.id}">
                    <i class="fa-solid fa-pen"></i>
                </button>
                <button class="session-action-btn delete" title="Xóa" data-action="delete" data-id="${session.id}">
                    <i class="fa-solid fa-trash"></i>
                </button>
            </div>
        `;

        // Click on item → switch session
        item.addEventListener('click', (e) => {
            // Don't trigger if clicking action buttons
            if (e.target.closest('[data-action]')) return;
            switchSession(session.id);
        });

        // Action buttons
        item.querySelectorAll('[data-action]').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const action = btn.dataset.action;
                const id = btn.dataset.id;
                if (action === 'rename') renameSession(id);
                if (action === 'delete') deleteSession(id);
            });
        });

        sidebarSessions.appendChild(item);
    });
}

/** Format an ISO timestamp as a relative label ("Vừa xong", "2 giờ trước", etc.) */
function formatRelativeTime(isoString) {
    if (!isoString) return '';
    const date = new Date(isoString + 'Z'); // treat as UTC
    const now = new Date();
    const diffMs = now - date;
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return 'Vừa xong';
    if (diffMin < 60) return `${diffMin} phút trước`;
    const diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return `${diffH} giờ trước`;
    const diffD = Math.floor(diffH / 24);
    if (diffD < 7) return `${diffD} ngày trước`;
    return date.toLocaleDateString('vi-VN');
}

/** Create a brand new session and switch to it */
async function createNewSession() {
    try {
        const res = await fetch('/api/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: 'Cuộc trò chuyện mới' }),
        });
        if (!res.ok) return;
        const newSession = await res.json();
        currentSessionId = newSession.id;
        await loadSessions();
        clearChatUI();
        updateSessionTitleDisplay('Cuộc trò chuyện mới');
        btnRename.style.display = 'flex';
        chatInput.focus();
        // On mobile: close sidebar after creating so chat is visible
        if (isMobile()) closeSidebar();
    } catch (err) {
        console.error('Failed to create session:', err);
    }
}

/** Switch to an existing session — load and render its messages */
async function switchSession(sessionId) {
    if (sessionId === currentSessionId) {
        if (isMobile()) closeSidebar();
        return;
    }
    currentSessionId = sessionId;

    // Update active highlight immediately
    document.querySelectorAll('.session-item').forEach(el => {
        el.classList.toggle('active', el.dataset.id === sessionId);
    });

    try {
        const res = await fetch(`/api/sessions/${sessionId}`);
        if (!res.ok) return;
        const session = await res.json();

        clearChatUI(false);   // clear without adding welcome message
        updateSessionTitleDisplay(session.title);
        btnRename.style.display = 'flex';

        // Render all stored messages
        if (session.messages && session.messages.length > 0) {
            chatSuggestions.style.display = 'none';
            session.messages.forEach(msg => {
                appendMessage(msg.role === 'user' ? 'user' : 'agent', msg.content);
            });
        } else {
            chatSuggestions.style.display = 'flex';
            appendWelcomeMessage();
        }

        if (window.innerWidth <= 900) closeSidebar();
    } catch (err) {
        console.error('Failed to switch session:', err);
    }
}

/** Rename a session via prompt */
async function renameSession(sessionId) {
    const session = sessions.find(s => s.id === sessionId);
    const current = session ? session.title : '';
    const newTitle = prompt('Đặt tên cuộc trò chuyện:', current);
    if (!newTitle || !newTitle.trim()) return;

    try {
        const res = await fetch(`/api/sessions/${sessionId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: newTitle.trim() }),
        });
        if (!res.ok) return;
        await loadSessions();
        if (sessionId === currentSessionId) {
            updateSessionTitleDisplay(newTitle.trim());
        }
    } catch (err) {
        console.error('Failed to rename session:', err);
    }
}

/** Rename currently active session (from header button) */
async function renameCurrentSession() {
    if (!currentSessionId) return;
    await renameSession(currentSessionId);
}

/** Delete a session */
async function deleteSession(sessionId) {
    const session = sessions.find(s => s.id === sessionId);
    const title = session ? session.title : 'cuộc trò chuyện này';
    if (!confirm(`Xóa "${title}"? Hành động này không thể hoàn tác.`)) return;

    try {
        await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
        await loadSessions();

        // If the deleted session was active, reset to blank
        if (sessionId === currentSessionId) {
            currentSessionId = null;
            clearChatUI();
            updateSessionTitleDisplay('Trò chuyện với tiếp tân');
            btnRename.style.display = 'none';

            // Switch to the most recent session if any
            if (sessions.length > 0) {
                switchSession(sessions[0].id);
            }
        }
    } catch (err) {
        console.error('Failed to delete session:', err);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// UI helpers
// ─────────────────────────────────────────────────────────────────────────────
function updateSessionTitleDisplay(title) {
    if (sessionTitle) sessionTitle.textContent = title;
}

/** Clear the chat history area */
function clearChatUI(addWelcome = true) {
    chatHistory.innerHTML = '';
    if (addWelcome) {
        appendWelcomeMessage();
        chatSuggestions.style.display = 'flex';
    }
}

function appendWelcomeMessage() {
    const el = document.createElement('div');
    el.classList.add('message', 'system-message');
    el.innerHTML = `
        <div class="message-avatar"><i class="fa-solid fa-robot"></i></div>
        <div class="message-content">
            <p>Xin chào! Tôi là <strong>Tiếp tân y tế thông minh</strong> tại phòng khám. Tôi có thể giúp bạn:</p>
            <ul>
                <li>Phân tích triệu chứng và giới thiệu chuyên khoa khám thích hợp.</li>
                <li>Tra cứu lịch trực trống của các bác sĩ.</li>
                <li>Hỗ trợ đăng ký và xác nhận lịch hẹn khám ngay lập tức.</li>
            </ul>
            <p>Hãy miêu tả chi tiết tình trạng sức khỏe hoặc triệu chứng của bạn để chúng ta bắt đầu nhé!</p>
        </div>
    `;
    chatHistory.appendChild(el);
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// ─────────────────────────────────────────────────────────────────────────────
// Chat form submission
// ─────────────────────────────────────────────────────────────────────────────
chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (isProcessing) return;
    const message = chatInput.value.trim();
    if (!message) return;
    await sendMessage(message);
});

async function useSuggestion(button) {
    if (isProcessing) return;
    const text = button.innerText;
    chatInput.value = '';
    await sendMessage(text);
}

// ─────────────────────────────────────────────────────────────────────────────
// Send message to backend
// ─────────────────────────────────────────────────────────────────────────────
async function sendMessage(text) {
    isProcessing = true;
    chatInput.value = '';
    chatInput.disabled = true;
    btnSubmit.disabled = true;

    // Hide suggestions after first message
    chatSuggestions.style.display = 'none';

    appendMessage('user', text);

    const typingIndicator = appendTypingIndicator();
    const startTime = performance.now();

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message: text,
                session_id: currentSessionId,   // ← send current session
            }),
        });

        const duration = Math.round(performance.now() - startTime);

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || 'Failed to get reply');
        }

        const data = await response.json();

        // Update current session id from response (auto-created if was null)
        if (data.session_id && data.session_id !== currentSessionId) {
            currentSessionId = data.session_id;
            btnRename.style.display = 'flex';
        }

        typingIndicator.remove();
        appendMessage('agent', data.reply);

        // Refresh sidebar list to show updated time / new session
        await loadSessions();

    } catch (error) {
        typingIndicator.remove();
        appendMessage('agent', `❌ Có lỗi xảy ra: ${error.message}. Vui lòng thử lại sau.`);
    } finally {
        isProcessing = false;
        chatInput.disabled = false;
        btnSubmit.disabled = false;
        chatInput.focus();
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Message rendering
// ─────────────────────────────────────────────────────────────────────────────
function appendMessage(sender, text) {
    const messageDiv = document.createElement('div');
    // 'agent' maps to system-message style class
    const cssClass = sender === 'user' ? 'user-message' : 'system-message';
    messageDiv.classList.add('message', cssClass);

    const avatar = document.createElement('div');
    avatar.classList.add('message-avatar');
    avatar.innerHTML = sender === 'user'
        ? '<i class="fa-solid fa-user"></i>'
        : '<i class="fa-solid fa-robot"></i>';

    const content = document.createElement('div');
    content.classList.add('message-content');

    // Basic markdown-ish formatting
    let formattedText = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\n/g, '<br>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`([^`]+)`/g, '<code>$1</code>');

    content.innerHTML = `<p>${formattedText}</p>`;

    messageDiv.appendChild(avatar);
    messageDiv.appendChild(content);
    chatHistory.appendChild(messageDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;

    return messageDiv;
}

function appendTypingIndicator() {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', 'system-message');

    const avatar = document.createElement('div');
    avatar.classList.add('message-avatar');
    avatar.innerHTML = '<i class="fa-solid fa-robot"></i>';

    const content = document.createElement('div');
    content.classList.add('message-content');
    content.innerHTML = `
        <div style="display:flex;gap:4px;align-items:center;padding:4px 6px;">
            <span class="pulse-dot" style="width:6px;height:6px;"></span>
            <span class="pulse-dot" style="width:6px;height:6px;animation-delay:0.2s;"></span>
            <span class="pulse-dot" style="width:6px;height:6px;animation-delay:0.4s;"></span>
        </div>
    `;

    messageDiv.appendChild(avatar);
    messageDiv.appendChild(content);
    chatHistory.appendChild(messageDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;

    return messageDiv;
}

// ─────────────────────────────────────────────────────────────────────────────
// Config fetch
// ─────────────────────────────────────────────────────────────────────────────
async function fetchConfig() {
    try {
        const response = await fetch('/api/config');
        if (response.ok) {
            const data = await response.json();
            const providerBadge = document.getElementById('provider-badge');
            const modelBadge    = document.getElementById('model-badge');
            const sidebarBadge  = document.getElementById('provider-badge-sidebar');
            if (providerBadge) providerBadge.innerText = data.provider;
            if (modelBadge)    modelBadge.innerText = data.model;
            if (sidebarBadge)  sidebarBadge.innerText = data.provider;
        }
    } catch (error) {
        console.error('Error fetching config:', error);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Close context menu on outside click
// ─────────────────────────────────────────────────────────────────────────────
document.addEventListener('click', (e) => {
    if (!contextMenu.contains(e.target)) {
        contextMenu.style.display = 'none';
        ctxTargetId = null;
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// Init
// ─────────────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    await fetchConfig();
    await loadSessions();

    // Auto-switch to most recent session on load
    if (sessions.length > 0) {
        await switchSession(sessions[0].id);
    }
});
