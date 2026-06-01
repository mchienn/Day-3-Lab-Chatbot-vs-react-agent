# Individual Report: Lab 3 - Chatbot vs ReAct Agent

- **Student Name**: Nguyễn Minh Chiến
- **Student ID**: 2A202600664
- **Date**: 01/06/2026

---

## I. Technical Contribution (15 Points)

I was responsible for building the core agent system, telemetry infrastructure, monitoring dashboard, and CLI chatbot interface. Below are the specific modules I implemented:

### 1. ReAct Agent (`src/agent/agent.py`)

Implemented the full ReAct (Reasoning + Acting) loop that drives the intelligent symptom triage system:

- **Core ReAct loop**: `Thought → Action → Observation → Final Answer` cycle with configurable `max_steps` (default 5)
- **System prompt engineering**: Designed a detailed system prompt with symptom analysis rules, context awareness instructions, and format constraints to guide the LLM's reasoning
- **Conversation history management**: Added `_build_prompt_with_history()` to maintain multi-turn context, solving the critical issue of the LLM "forgetting" previously mentioned symptoms
- **Edge case handling**: Implemented `FALLBACK_RESPONSES` for empty input, out-of-scope queries, LLM errors, rate limits, and max-step termination
- **Out-of-scope detection**: `_is_clearly_out_of_scope()` filters non-medical queries (weather, sports, politics) while preserving medical context

```python
# Key: Conversation history injection for context awareness
def _build_prompt_with_history(self, user_input: str) -> str:
    history_lines = []
    for entry in self.conversation_history[-5:]:
        history_lines.append(f"Patient: {entry['user']}")
        history_lines.append(f"Agent: {entry['agent']}")
    return f"CONVERSATION HISTORY:\n{history_text}\n\nCURRENT MESSAGE:\nPatient: {user_input}"
```

### 2. Telemetry System (`src/telemetry/`)

Built industry-grade observability for debugging and performance analysis:

- **`logger.py`**: Structured JSON logger (`IndustryLogger`) that outputs to both console and daily log files (`logs/YYYY-MM-DD.log`) in NDJSON format
- **`metrics.py`**: `PerformanceTracker` class with:
  - Per-request metrics: tokens (prompt/completion/total), latency, cost estimate, tokens/sec, token ratio
  - Tool usage frequency tracking
  - Session-level summaries with aggregated stats
  - Historical metrics persistence across sessions
  - Report export to `reports/session_YYYYMMDD_HHMMSS.json`
  - Industry pricing config for cost calculation (Gemini, GPT-4o)

### 3. Monitoring Dashboard (`monitoring.py` + `static/monitoring/`)

Designed and built a full real-time monitoring dashboard running on a separate port (8001):

- **Backend** (`monitoring.py`): FastAPI server with endpoints:
  - `GET /api/monitoring/historical` — aggregated stats from report files
  - `GET /api/monitoring/tools` — tool usage frequency
  - `GET /api/monitoring/logs` — recent log entries
  - `GET /api/monitoring/reports/{filename}` — session detail
- **Frontend** (`static/monitoring/`): Dark-themed dashboard with:
  - Stats cards (sessions, cost, tokens, latency, tokens/sec, success rate)
  - Tool usage bar chart
  - Live log stream with color-coded events
  - Session history table with detail modal
  - Auto-refresh every 10 seconds

### 4. CLI Chatbot (`chatbot.py`)

Built an interactive command-line chatbot for rapid testing:

- Provider-agnostic (Google Gemini, OpenAI) via `LLMProvider` interface
- Session management with `new`/`reset` command to clear history
- Windows UTF-8 support
- Timing output per response for performance observation

---

## II. Debugging Case Study (10 Points)

### Problem: LLM Forgets Previous Symptoms in Multi-Turn Conversation

**Scenario**: User says "đau bụng, đầy hơi" → Agent identifies Khoa Tiêu hóa. User then says "ngày mai" to book an appointment → Agent asks "Bạn bị triệu chứng gì?" instead of proceeding with booking.

**Log Source** (`logs/2026-06-01.log`):
```json
{"event": "AGENT_START", "data": {"input": "ngày mai"}}
{"event": "LLM_RESPONSE", "data": {"content": "Thought: The patient hasn't described any symptoms yet...\nFinal Answer: Bạn có thể mô tả triệu chứng của mình không?"}}
```

**Diagnosis**: The agent was constructed fresh per request in `main.py` (`chat_endpoint`), so `conversation_history` was always empty. The LLM had no access to prior messages — it was architecturally impossible for it to remember context.

**Root Cause**: In `main.py`, each API call created a new `ReActAgent` instance:
```python
agent = ReActAgent(llm=provider, tools=tools, max_steps=5)
# conversation_history = [] ← always empty!
```

**Solution**: Two-part fix:
1. **Session persistence**: In `main.py`, load previous messages from the session JSON and inject them into `agent.conversation_history` before running:
```python
if session and "messages" in session:
    history = []
    user_msg = None
    for msg in session["messages"]:
        if msg["role"] == "user":
            user_msg = msg["content"]
        elif msg["role"] == "agent" and user_msg:
            history.append({"user": user_msg, "agent": msg["content"]})
            user_msg = None
    agent.conversation_history = history
```

2. **Prompt injection**: `_build_prompt_with_history()` prepends the last 5 exchanges to the prompt with an explicit instruction: *"Based on the conversation history above, the patient has already provided symptoms. Do NOT ask for symptoms again."*

**Result**: After fix, the agent correctly handles multi-turn flows:
- "đau bụng" → identifies Khoa Tiêu hóa
- "ngày mai" → proceeds to check doctor availability without re-asking symptoms

---

## III. Personal Insights: Chatbot vs ReAct (10 Points)

### 1. Reasoning: The Power of the `Thought` Block

The `Thought` block transforms the LLM from a reactive responder into a deliberate reasoner. In the chatbot baseline, when a user says "đau bụng, đầy hơi, khó tiêu", the LLM might respond with generic advice or ask clarifying questions. With the ReAct pattern, the `Thought` forces explicit reasoning:

```
Thought: The patient has gastrointestinal symptoms. I should use AnalyzeSymptomTool to identify the specialty.
Action: AnalyzeSymptomTool("đau bụng, đầy hơi, khó tiêu")
```

This structured reasoning chain made the agent **dramatically more reliable** for multi-step tasks. The key insight: LLMs perform better when they "show their work" — the Thought block externalizes internal reasoning, making it debuggable and correctable.

### 2. Reliability: When the Agent Performs Worse

The Agent actually performed **worse** than the Chatbot in two scenarios:

- **Simple greetings**: "Xin chào" or "Cảm ơn" — the Agent would try to invoke tools unnecessarily or produce overly structured responses, while a simple chatbot handles these naturally.
- **Rate-limited environments**: Under Gemini free-tier limits (5-20 requests), the Agent's multi-step loop consumes quota faster. A single user query might use 2-3 LLM calls (Thought → Action → Final Answer) vs. 1 call for a chatbot.

The Agent's strength is **complex, multi-step queries** (symptom → specialty → doctor availability → booking). For simple Q&A, the overhead isn't worth it.

### 3. Observation: Environment Feedback as a Reasoning Anchor

The `Observation` from tool execution is the most critical part of the loop. Without it, the LLM would hallucinate tool results. With real observations, the agent's next `Thought` is grounded in facts:

```
Action: AnalyzeSymptomTool("đau bụng")
Observation: {"specialty": "Khoa Tiêu hóa"}
Thought: The tool confirmed Gastroenterology. Now I need to check doctor availability.
```

This creates a **feedback loop** where each step builds on verified data rather than LLM assumptions. The observation acts as a "reality check" that prevents hallucination cascades.

---

## IV. Future Improvements (5 Points)

### Scalability

- **Async tool execution**: Use `asyncio` for concurrent tool calls (e.g., check multiple doctor schedules simultaneously)
- **Queue-based architecture**: Replace direct LLM calls with a message queue (Redis/RabbitMQ) to handle burst traffic and retry logic
- **Database-backed sessions**: Move from JSON file storage to PostgreSQL for concurrent access and better query capabilities

### Safety

- **Supervisor LLM**: Add a second LLM pass that audits the agent's actions before execution — checking for inappropriate medical advice, hallucinated tools, or unsafe recommendations
- **Input sanitization**: Validate and sanitize user inputs more rigorously to prevent prompt injection attacks
- **Rate limiting per user**: Implement per-session rate limits to prevent abuse and manage API costs

### Performance

- **Prompt caching**: Use Gemini's context caching for the system prompt to reduce token costs by ~50%
- **Tool retrieval with RAG**: When the number of tools grows beyond 10+, use vector similarity to dynamically select relevant tools instead of listing all tools in the prompt
- **Streaming responses**: Implement SSE (Server-Sent Events) for real-time token streaming to improve perceived latency from 2-3s to near-instant

---

> [!NOTE]
> Submit this report by renaming it to `REPORT_[YOUR_NAME].md` and placing it in this folder.
