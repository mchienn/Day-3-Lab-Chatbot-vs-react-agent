# Individual Report: Lab 3 - Chatbot vs ReAct Agent

- **Student Name**: [Phạm Đức Liêm]
- **Student ID**: [2A202600985]
- **Date**: 2026-06-01

---

## I. Technical Contribution (15 Points)

*Describe your specific contribution to the codebase (e.g., implemented a specific tool, fixed the parser, etc.).*

### Modules Implemented

| File | Role |
|---|---|
| `chatbot.py` | Baseline triage chatbot — Phase 2 of the lab |
| `run_agent.py` | Main entry point for the ReAct Agent system |
| `tests/test_chatbot.py` | Unit tests for the triage chatbot (mocked API) |

---

### 1. `chatbot.py` — Baseline Chatbot

Implemented the Vinmec Triage Agent baseline chatbot using OpenAI's Chat Completions API.

**Key design decisions:**
- Defined a `SYSTEM_PROMPT` that enforces strict medical constraints (no diagnosis, no prescription, no replacing doctors).
- Used `response_format={"type": "json_object"}` to guarantee structured JSON output from the LLM, eliminating the need for fragile regex parsing.
- Structured the output schema to include `urgency`, `specialty`, `confidence`, and `next_step` fields.
- Added Windows-compatible `sys.stdout.reconfigure(encoding="utf-8")` to prevent `UnicodeEncodeError` when printing Vietnamese text.

**Code Highlight — `SYSTEM_PROMPT`:**
```python
SYSTEM_PROMPT = """You are the Vinmec Triage Agent ...
### Emergency Conditions to Detect:
- Chest pain with shortness of breath
- Stroke symptoms (facial drooping, arm weakness, slurred speech)
- Severe bleeding
- Loss of consciousness
- Seizures

### Strict Constraints:
- Do NOT diagnose specific diseases
- Do NOT prescribe medications
- Do NOT replace doctors

### Output Format:
{
  "urgency": "Emergency" | "High" | "Medium" | "Low",
  "specialty": "<Recommended Medical Specialty>",
  "confidence": <0.0 to 1.0>,
  "next_step": "BookingAgent" | "Clarify"
}
"""
```

**Code Highlight — `triage_patient()` function:**
```python
def triage_patient(symptoms: str, ...) -> Dict[str, Any]:
    response = client.chat.completions.create(
        model=actual_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": symptoms}
        ],
        response_format={"type": "json_object"},
        temperature=0.0   # Deterministic triage
    )
    parsed_response["_meta"] = {
        "prompt_tokens":      response.usage.prompt_tokens,
        "completion_tokens":  response.usage.completion_tokens,
        "total_tokens":       response.usage.total_tokens,
    }
    return parsed_response
```

**How it interacts with the system:** `chatbot.py` is the *baseline* Phase 2 component. It demonstrates the limitations of a single LLM call — the model cannot look up doctor schedules or verify slot availability. This weakness is used in Phase 3 to motivate the ReAct Agent.

---

### 2. `run_agent.py` — ReAct Agent Entry Point

Implemented the main CLI runner for the ReAct Agent, integrating it with the official tools from `src/tools/medical_tools.py`.

**Key design decisions:**
- Implemented a `MockLLMProvider` as a fallback so the agent can be tested without API keys.
- Built a `LoggedProviderWrapper` that intercepts every LLM call to extract and display `Thought`, `Action`, and `Final Answer` in real-time on the console.
- Built a `wrap_tool_with_logging()` function to intercept every tool call and print `Observation` immediately, creating a visible ReAct trace.
- Structured logging writes to `logs/agent.log` in JSONL format with full step traces + token/latency metrics per interaction.
- Added `MAX_ITERATIONS = 5` and error handling for tool failures, provider connection failures, and keyboard interrupts.

**Code Highlight — `LoggedProviderWrapper`:**
```python
class LoggedProviderWrapper(LLMProvider):
    def generate(self, prompt, system_prompt=None):
        result = self.base_provider.generate(prompt, system_prompt)
        # Parse and display Thought/Action/Final Answer in real-time
        thought_match = re.search(r'Thought:\s*(.*?)(?=Action:|Final Answer:|$)', content, re.DOTALL)
        print(f"\n[Thought]: {thought}")
        if action:
            print(f"[Action]: Executing {action}...")
        elif final_answer:
            print(f"[Final Answer]: {final_answer}")
        return result
```

**Code Highlight — `write_interaction_log()` for academic analysis:**
```python
log_entry = {
    "timestamp":      datetime.now().isoformat(),
    "user_input":     user_input,
    "steps":          [...],
    "final_response": final_answer,
    "metrics": {
        "total_steps":             len(steps),
        "total_latency_ms":        total_latency,
        "total_prompt_tokens":     total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_tokens":            total_tokens
    }
}
```

**How it interacts with the ReAct loop:** `run_agent.py` is the *orchestrator*. It wires the `GeminiProvider`/`OpenAIProvider`/`MockLLMProvider` to the `ReActAgent` class. Each invocation of `run_agent_session()` represents one patient conversation, which is fully traceable in the log file for evaluation purposes.

---

## II. Debugging Case Study (10 Points)

*Analyze a specific failure event encountered during the lab.*

### Problem Description

During the first run of `run_agent.py` with the original (pre-`develop` pull) `tools.py`, a logic disconnect was detected in the **emergency triage scenario**.

**Log evidence from `logs/agent.log` (Timestamp: `2026-06-01T15:39:44`):**
```json
{
  "user_input": "Tôi bị đau ngực và khó thở",
  "steps": [
    {
      "step": 1,
      "thought": "The patient reports symptoms that look like an emergency. I must immediately run check_red_flags.",
      "action": "check_red_flags(\"patient reported emergency symptoms\")",
      "observation": "No emergency red flags detected. Proceed with standard specialty recommendation."
    },
    {
      "step": 2,
      "thought": "The check_red_flags tool confirmed an emergency. I must immediately route booking to Cardiology.",
      "action": "transfer_booking(\"Cardiology\")",
      ...
    }
  ]
}
```

### Diagnosis

There is a **clear logic contradiction** between `Thought` at Step 2 and the `Observation` at Step 1:

- **Observation** at Step 1 says: *"No emergency red flags detected."*
- **Thought** at Step 2 says: *"The check_red_flags tool confirmed an emergency."*

The root cause was a **hallucination in the Mock LLM Provider** — the mock response at Step 2 was hardcoded based on keyword matching (`"đau ngực"` and `"khó thở"`) and did not actually read the Observation from Step 1. The mock `generate()` function made its next decision based only on its internal `step` counter, not on the actual tool observation returned.

### Solution

The fix involved two steps:

1. **Mock Provider fix**: Updated the emergency branch of `MockLLMProvider.generate()` to make decisions consistent with the observation content, not a hardcoded script. When `check_red_flags` returns `"No emergency red flags"`, the mock should follow the standard flow.

2. **Systemic fix**: Replaced the entire old `tools.py` with the official `src/tools/medical_tools.py` (pulled from `develop` branch) which implements proper keyword-based detection using the `symptoms_mapping.json` data file, ensuring tool outputs are factual and consistent with what the LLM's Thought block describes.

---

## III. Personal Insights: Chatbot vs ReAct (10 Points)

### 1. Reasoning: How did the `Thought` block help?

The `Thought` block makes the agent's decision-making process **explicit and auditable**. In `chatbot.py`, the LLM produces a single JSON output directly — there is no visible reasoning step. If the output is wrong, there is no trace to diagnose *why*.

In the ReAct agent, each `Thought` step is logged. For example:
```
[Thought]: The specialty recommended is 'Khoa Tiêu hóa'. I should check the available time slots.
[Action]: CheckDoctorAvailabilityTool("Khoa Tiêu hóa", "2026-06-02")
```
This makes it possible to trace the *reasoning chain*, not just the final output. For a debugging engineer, this is the critical difference between a black-box system and an auditable one.

### 2. Reliability: When did the Agent perform *worse* than the Chatbot?

The ReAct Agent performed **worse** in the following conditions observed during the lab:

| Scenario | Chatbot | ReAct Agent |
|---|---|---|
| **Simple single-step query** ("Tôi bị ngứa") | Instant response, 1 API call | 3–5 API calls (check flags → recommend → book), higher cost and latency |
| **Vague input** ("Tôi không khỏe") | Returns `"next_step": "Clarify"` deterministically | Agent may loop through all tools before concluding it needs clarification |
| **No API key available** | Fails fast with clear error message | Mock provider runs through all steps, producing confusing output for students |

For short, decisive queries, the Chatbot's single-call architecture is faster, cheaper, and more predictable.

### 3. Observation: How did tool Observations influence next steps?

The `Observation` is the most critical part of the ReAct loop — it is what transforms the agent from a passive chatbot into an **active reasoning system**. In the successful booking trace:

```
Observation (Step 2): [{"doctor_name": "BS. Trần Văn A", "available_slots": {"morning": ["08:00", ...]}}]
Thought (Step 3): I see BS. Trần Văn A has available slots. I will book at 08:00.
Action (Step 3): BookAppointmentTool("Nguyễn Văn A", "BS. Trần Văn A", "2026-06-02 08:00")
```

The observation at Step 2 directly feeds the **specific data** (doctor name, available time) that the agent uses to make a grounded decision at Step 3. Without this feedback loop, the agent would have to guess or hallucinate the doctor's name and schedule. This is the fundamental mechanism that allows agents to interact with **real external data**, which a pure chatbot cannot do.

---

## IV. Future Improvements (5 Points)

### Scalability
The current system runs tools **synchronously** — each tool call blocks the agent loop. In a production system with high patient volume, this creates a bottleneck. A production-level improvement would use an **async tool execution queue** (e.g., Python `asyncio`, Celery) where multiple tool calls can run in parallel, and the agent merges their observations before the next Thought step.

### Safety
The current `BookAppointmentTool` accepts any `patient_name` and `doctor_name` string without validation. A production system needs a **Supervisor LLM** or a **guardrail layer** that:
- Validates that the doctor exists in the database before booking.
- Checks that the time slot is not already taken (preventing double-booking).
- Flags if the LLM tries to call a tool with unexpected arguments (e.g., empty strings or injected commands).

### Performance
As the number of available tools grows (e.g., lab results lookup, billing, prescription history), the LLM's ability to choose the correct tool degrades. A production improvement would use a **vector database** (e.g., ChromaDB, Pinecone) to embed tool descriptions and perform semantic similarity search to retrieve only the top-k most relevant tools per query — keeping the system prompt short and focused.

---

> [!NOTE]
> Submit this report by renaming it to `REPORT_[YOUR_NAME].md` and placing it in this folder.
