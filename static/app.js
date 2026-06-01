// Elements
const chatHistory = document.getElementById('chat-history');
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const btnSubmit = document.getElementById('btn-submit');
const consoleBody = document.getElementById('console-body');

// Metrics elements
const metricLatency = document.getElementById('metric-latency');
const metricTokens = document.getElementById('metric-tokens');
const metricSteps = document.getElementById('metric-steps');
const metricStatus = document.getElementById('metric-status');

// Configuration
let isProcessing = false;

// Handle Form Submission
chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (isProcessing) return;
    
    const message = chatInput.value.trim();
    if (!message) return;
    
    await sendMessage(message);
});

// Use suggestions
async function useSuggestion(button) {
    if (isProcessing) return;
    const text = button.innerText;
    chatInput.value = '';
    await sendMessage(text);
}

// Send message to FastAPI Backend
async function sendMessage(text) {
    isProcessing = true;
    chatInput.value = '';
    chatInput.disabled = true;
    btnSubmit.disabled = true;
    
    // Add user message to UI
    appendMessage('user', text);
    
    // Reset and prepare console if it exists
    if (consoleBody) consoleBody.innerHTML = '';
    updateMetrics({
        status: 'Thinking...',
        latency: 'Calculating...',
        tokens: '...',
        steps: '0 / 5'
    });
    
    // Add typing indicator for agent
    const typingIndicator = appendTypingIndicator();
    
    const startTime = performance.now();
    
    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message: text })
        });
        
        const duration = Math.round(performance.now() - startTime);
        
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || 'Failed to get reply');
        }
        
        const data = await response.json();
        
        // Remove typing indicator
        typingIndicator.remove();
        
        // Render agent reply
        appendMessage('agent', data.reply);
        
        // Animate/render agent logs in the telemetry console
        await renderTelemetryLogs(data.logs, duration);
        
    } catch (error) {
        typingIndicator.remove();
        appendMessage('agent', `❌ Có lỗi xảy ra: ${error.message}. Vui lòng thử lại sau.`);
        updateMetrics({
            status: 'Error',
            latency: 'N/A',
            tokens: '0',
            steps: '0'
        });
        
        if (consoleBody) {
            consoleBody.innerHTML = `
                <div class="log-block" style="border-left-color: #EF4444;">
                    <div class="log-header">
                        <span class="log-title" style="color: #EF4444;">[SYSTEM_ERROR]</span>
                    </div>
                    <div class="log-body" style="color: #F87171;">
                        ${error.message}
                    </div>
                </div>
            `;
        }
    } finally {
        isProcessing = false;
        chatInput.disabled = false;
        btnSubmit.disabled = false;
        chatInput.focus();
    }
}

// Append Message Bubble to Chat History
function appendMessage(sender, text) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', `${sender}-message`);
    
    const avatar = document.createElement('div');
    avatar.classList.add('message-avatar');
    if (sender === 'user') {
        avatar.innerHTML = '<i class="fa-solid fa-user"></i>';
    } else {
        avatar.innerHTML = '<i class="fa-solid fa-robot"></i>';
    }
    
    const content = document.createElement('div');
    content.classList.add('message-content');
    
    // Formatting basic medical messages (handling newlines & markdown-like elements)
    let formattedText = text
        .replace(/\n/g, '<br>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`([^`]+)`/g, '<code>$1</code>');
        
    content.innerHTML = `<p>${formattedText}</p>`;
    
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(content);
    chatHistory.appendChild(messageDiv);
    
    // Scroll chat history to bottom
    chatHistory.scrollTop = chatHistory.scrollHeight;
    
    return messageDiv;
}

// Append typing indicator
function appendTypingIndicator() {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', 'system-message');
    
    const avatar = document.createElement('div');
    avatar.classList.add('message-avatar');
    avatar.innerHTML = '<i class="fa-solid fa-robot"></i>';
    
    const content = document.createElement('div');
    content.classList.add('message-content');
    content.innerHTML = `
        <div style="display: flex; gap: 4px; align-items: center; padding: 4px 8px;">
            <span class="pulse-dot" style="width: 6px; height: 6px;"></span>
            <span class="pulse-dot" style="width: 6px; height: 6px; animation-delay: 0.2s;"></span>
            <span class="pulse-dot" style="width: 6px; height: 6px; animation-delay: 0.4s;"></span>
        </div>
    `;
    
    messageDiv.appendChild(avatar);
    messageDiv.appendChild(content);
    chatHistory.appendChild(messageDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;
    
    return messageDiv;
}

// Update dashboard metrics if they exist in DOM
function updateMetrics({ status, latency, tokens, steps }) {
    if (status !== undefined && metricStatus) metricStatus.innerText = status;
    if (latency !== undefined && metricLatency) metricLatency.innerText = latency;
    if (tokens !== undefined && metricTokens) metricTokens.innerText = tokens;
    if (steps !== undefined && metricSteps) metricSteps.innerText = steps;
}

// Animate/Render logs step-by-step
async function renderTelemetryLogs(logs, durationMs) {
    if (!consoleBody) {
        // Just finalize metrics if they exist
        updateMetrics({
            status: 'Completed',
            latency: `${durationMs} ms`
        });
        return;
    }

    if (!logs || logs.length === 0) {
        consoleBody.innerHTML = `
            <div class="console-placeholder">
                <p>Không có telemetry logs nào được ghi lại.</p>
            </div>
        `;
        return;
    }

    let tokenAccumulator = 0;
    let stepCount = 0;
    
    for (let index = 0; index < logs.length; index++) {
        const log = logs[index];
        const eventType = log.event;
        const data = log.data || {};
        const timestamp = log.timestamp ? log.timestamp.split('T')[1].substring(0, 8) : '';
        
        let blockHtml = '';
        
        if (eventType === 'AGENT_START') {
            blockHtml = `
                <div class="log-block" style="border-left-color: var(--accent-secondary);">
                    <div class="log-header">
                        <span class="log-title agent-start">[AGENT_START]</span>
                        <span>${timestamp}</span>
                    </div>
                    <div class="log-body">
                        Tác vụ tiếp nhận: "${data.user_input}"
                    </div>
                </div>
            `;
        } 
        
        else if (eventType === 'LLM_RESPONSE') {
            stepCount = (data.step || 0) + 1;
            
            // Accumulate tokens if present
            if (data.usage && data.usage.total_tokens) {
                tokenAccumulator = data.usage.total_tokens;
            }
            
            // Format thought block
            const content = data.content || '';
            const thoughtMatch = content.match(/Thought:([\s\S]*?)(Action:|Final Answer:|$)/i);
            const thoughtText = thoughtMatch ? thoughtMatch[1].trim() : content;
            
            let actionHtml = '';
            const actionMatch = content.match(/Action:\s*(\w+)\((.*?)\)/i);
            if (actionMatch) {
                actionHtml = `
                    <div class="log-body action" style="margin-top: 8px;">
                        ➡️ Action: ${actionMatch[1]}(${actionMatch[2]})
                    </div>
                `;
            }
            
            blockHtml = `
                <div class="log-block" style="border-left-color: #A78BFA;">
                    <div class="log-header">
                        <span class="log-title llm-response">[STEP_${stepCount}_REASONING]</span>
                        <span>${timestamp}</span>
                    </div>
                    <div class="log-body thought">
                        Thought: ${thoughtText}
                    </div>
                    ${actionHtml}
                </div>
            `;
            
            // Live update metrics during simulation
            updateMetrics({
                steps: `${stepCount} / 5`,
                tokens: `${tokenAccumulator} total`
            });
        } 
        
        else if (eventType === 'TOOL_CALL') {
            blockHtml = `
                <div class="log-block" style="border-left-color: #F59E0B;">
                    <div class="log-header">
                        <span class="log-title tool-call">[TOOL_CALL]</span>
                        <span>${timestamp}</span>
                    </div>
                    <div class="log-body action">
                        Gọi công cụ: <strong style="color: #FFF;">${data.tool}</strong> với tham số <code>(${data.args})</code>
                    </div>
                </div>
            `;
        } 
        
        else if (eventType === 'TOOL_RESULT') {
            let resultText = data.result || '';
            let formattedJson = '';
            
            // Check if tool output is JSON and beautify it
            if (resultText.trim().startsWith('{') || resultText.trim().startsWith('[')) {
                try {
                    const parsed = JSON.parse(resultText);
                    formattedJson = `
                        <pre class="log-body json-data">${JSON.stringify(parsed, null, 2)}</pre>
                    `;
                    resultText = ''; // Hide raw string, display beautified JSON instead
                } catch (e) {
                    // Fallback to normal text if parsing fails
                }
            }
            
            blockHtml = `
                <div class="log-block" style="border-left-color: #10B981;">
                    <div class="log-header">
                        <span class="log-title tool-result">[TOOL_OBSERVATION]</span>
                        <span>${timestamp}</span>
                    </div>
                    ${resultText ? `<div class="log-body observation">Result: ${resultText}</div>` : ''}
                    ${formattedJson}
                </div>
            `;
        } 
        
        else if (eventType === 'AGENT_END') {
            const color = data.status === 'final_answer' ? '#10B981' : '#EF4444';
            blockHtml = `
                <div class="log-block" style="border-left-color: ${color};">
                    <div class="log-header">
                        <span class="log-title agent-end">[SESSION_COMPLETED]</span>
                        <span>${timestamp}</span>
                    </div>
                    <div class="log-body" style="color: ${color}; font-weight: bold;">
                        Status: ${data.status === 'final_answer' ? 'Xác thực thành công' : 'Dừng vòng lặp'}
                    </div>
                </div>
            `;
        }

        if (blockHtml) {
            // Append block
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = blockHtml;
            consoleBody.appendChild(tempDiv.firstElementChild);
            consoleBody.scrollTop = consoleBody.scrollHeight;
        }

        // Simulate animation timing (150ms per step to make it readable)
        await new Promise(resolve => setTimeout(resolve, 200));
    }
    
    // Finalize metrics
    updateMetrics({
        status: 'Completed',
        latency: `${durationMs} ms`,
        tokens: `${tokenAccumulator} total`,
        steps: `${stepCount} / 5`
    });
}

// Fetch active config from FastAPI backend
async function fetchConfig() {
    try {
        const response = await fetch('/api/config');
        if (response.ok) {
            const data = await response.json();
            const providerBadge = document.getElementById('provider-badge');
            const modelBadge = document.getElementById('model-badge');
            if (providerBadge) providerBadge.innerText = data.provider;
            if (modelBadge) modelBadge.innerText = data.model;
        }
    } catch (error) {
        console.error('Error fetching config:', error);
    }
}

// Initialize on load
document.addEventListener('DOMContentLoaded', fetchConfig);

