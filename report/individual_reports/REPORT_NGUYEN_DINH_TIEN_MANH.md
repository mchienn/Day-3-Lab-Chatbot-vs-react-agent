# Individual Report: Lab 3 - Chatbot vs ReAct Agent

- **Student Name**: Nguyễn Đức Mạnh
- **Student ID**: HE181128
- **Date**: 2026-06-01

---

## I. Technical Contribution (15 Points)

I was responsible for rebranding the UI/UX to match Vinmec Hospital standards, implementing the persistent chat history sidebar (both frontend and backend), refining the medical tooling, and resolving the rate limit crash.

- **Modules Implemented / Modified**:
  - `static/app.js` & `static/style.css`: Implemented the complete sidebar layout, session listing, dynamic renaming/deletion of chat sessions, and styled the UI to match Vinmec corporate colors (teal and white).
  - `main.py`: Created the backend FastAPI session management endpoints (`GET /api/sessions`, `POST /api/sessions`, `PUT /api/sessions/{session_id}`, `DELETE /api/sessions/{session_id}`) to store/load JSON session files.
  - `src/agent/agent.py`: Enhanced the `ReActAgent` class by integrating real-time system date context and fixing the parser to prevent tool-skipping.
  - `src/tools/medical_tools.py`: Standardized validation rules inside symptoms mapping and doctor schedule queries.

- **Code Highlights**:
  *Backend session endpoints in `main.py`:*
  ```python
  @app.post("/api/sessions", status_code=201)
  async def create_session(req: SessionCreateRequest):
      now = datetime.utcnow().isoformat()
      session = {
          "id": str(uuid.uuid4()),
          "title": req.title,
          "created_at": now,
          "updated_at": now,
          "messages": [],
      }
      _save_session(session)
      return {"id": session["id"], "title": session["title"], "created_at": now}
  ```

  *Real-time date injection in `src/agent/agent.py`:*
  ```python
  from datetime import datetime
  now = datetime.now()
  days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
  today_str = f"{now.strftime('%Y-%m-%d')} ({days[now.weekday()]})"
  ```

- **Documentation**:
  The frontend `app.js` sends the `session_id` along with every user message to `/api/chat`. The backend retrieves the session's chat history from the JSON database in `chat_sessions/` and appends the last 5 turns to the LLM prompt. This maintains context across page reloads.

---

## II. Debugging Case Study (10 Points)

I diagnosed and resolved a critical crash where the agent hit the 5 Requests Per Minute (RPM) free-tier rate limit of the Gemini API.

- **Problem Description**: 
  When the user entered "ngày mai" (tomorrow) or "có những ngày nào trống và có lịch", the agent repeatedly queried `CheckDoctorAvailabilityTool` for subsequent dates and crashed with a `429 Resource Exhausted` error.
- **Log Source**: `logs/2026-06-01.log`
  ```json
  {"step": 0, "tool": "CheckDoctorAvailabilityTool", "args": "Khoa Tiêu hóa\", \"2024-05-17"}
  {"step": 0, "tool": "CheckDoctorAvailabilityTool", "result": "No available doctors found..."}
  {"step": 1, "tool": "CheckDoctorAvailabilityTool", "args": "Khoa Tiêu hóa\", \"2024-05-18"}
  ...
  {"step": 4, "error": "Error connected Gemini API: 429 You exceeded your current quota..."}
  ```
- **Diagnosis**: 
  The LLM prompt lacked any knowledge of the current date. The model defaulted to assuming today was `2024-05-15`, which fell outside the mock schedule database range (`2026-06-02` - `2026-06-04`). Consequently, every date checked in 2024 returned "No available doctors". The model looped through 2024 dates sequentially in a single turn, triggering the API rate limit.
- **Solution**: 
  I dynamically injected the system's real-time date (e.g. `2026-06-01`) into the system prompt's `CONTEXT AWARENESS` instructions. This aligned the model's relative date calculations with the database, allowing it to locate available slots immediately on the first query without looping.

---

## III. Personal Insights: Chatbot vs ReAct (10 Points)

1. **Reasoning**: The `Thought` block enables the agent to decompose a user request into logical steps. Instead of blindly trying to answer, it reasons which data it lacks, selects the appropriate tool, and verifies the outcome before compiling the final response.
2. **Reliability**: ReAct agents can perform worse than simple chatbots if the parsing format is fragile. If the LLM omits keywords like `Action:` or `Final Answer:`, the agent can enter an infinite loop or throw execution errors.
3. **Observation**: Environmental feedback (Observations) serves as a grounding mechanism. When a tool returns a result, the model adjusts its reasoning (e.g., if a date is fully booked, the model observes this and suggests an alternative date).

---

## IV. Future Improvements (5 Points)

- **Scalability**: Shift from local session storage files to an elastic Redis cache to handle high concurrent user sessions.
- **Safety**: Implement a Guardrails layer (like Llama Guard or NeMo Guardrails) to detect medical diagnosis queries or off-topic prompt injections before they reach the ReAct agent.
- **Performance**: Move the symptom-to-specialty lookup from keyword matching to vector embedding searches (semantic triage) to support slang, complex descriptions, and typos.
