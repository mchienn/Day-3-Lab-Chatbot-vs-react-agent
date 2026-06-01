import warnings
# Suppress Google API version and package deprecation warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

import os
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import core modules
from src.core.gemini_provider import GeminiProvider
try:
    from src.core.local_provider import LocalProvider
    LOCAL_PROVIDER_AVAILABLE = True
except ImportError:
    LOCAL_PROVIDER_AVAILABLE = False
from src.agent.agent import ReActAgent
from src.tools.medical_tools import (
    AnalyzeSymptomTool,
    CheckDoctorAvailabilityTool,
    BookAppointmentTool
)

app = FastAPI(title="Vinmec Smart Clinic - Hệ Thống Tiếp Tân Thông Minh")

# ─────────────────────────────────────────────────────────────────────────────
# Session storage helpers
# ─────────────────────────────────────────────────────────────────────────────
SESSIONS_DIR = "chat_sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)


def _session_path(session_id: str) -> str:
    return os.path.join(SESSIONS_DIR, f"{session_id}.json")


def _load_session(session_id: str) -> Dict[str, Any]:
    path = _session_path(session_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_session(data: Dict[str, Any]) -> None:
    path = _session_path(data["id"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _list_sessions() -> List[Dict[str, Any]]:
    sessions = []
    for fname in os.listdir(SESSIONS_DIR):
        if fname.endswith(".json"):
            fpath = os.path.join(SESSIONS_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Return summary only (no full messages list)
                sessions.append({
                    "id": data["id"],
                    "title": data.get("title", "Cuộc trò chuyện mới"),
                    "created_at": data.get("created_at", ""),
                    "updated_at": data.get("updated_at", ""),
                    "message_count": len(data.get("messages", [])),
                })
            except Exception:
                pass
    # Sort newest first
    sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
    return sessions


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None   # ← NEW: attach message to a session


class ChatResponse(BaseModel):
    reply: str
    logs: List[Dict[str, Any]]
    session_id: str                     # ← NEW: returned so frontend can track


class SessionCreateRequest(BaseModel):
    title: Optional[str] = "Cuộc trò chuyện mới"


class SessionRenameRequest(BaseModel):
    title: str


# ─────────────────────────────────────────────────────────────────────────────
# LLM provider factory
# ─────────────────────────────────────────────────────────────────────────────
def get_llm_provider():
    """Instantiates the LLM provider configured in the .env file."""
    provider_name = os.getenv("DEFAULT_PROVIDER", "google").lower()
    model_name = os.getenv("DEFAULT_MODEL", "gemini-2.5-flash")

    if provider_name == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "your_openai_api_key_here":
            raise ValueError("OPENAI_API_KEY is not set or is invalid in .env")
        return OpenAIProvider(model_name=model_name, api_key=api_key)

    elif provider_name == "google":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or api_key == "your_gemini_api_key_here":
            raise ValueError("GEMINI_API_KEY is not set or is invalid in .env")
        return GeminiProvider(model_name=model_name, api_key=api_key)

    elif provider_name == "local":
        if not LOCAL_PROVIDER_AVAILABLE:
            raise ValueError("Local provider requires 'llama-cpp-python' package.")
        model_path = os.getenv("LOCAL_MODEL_PATH")
        if not model_path or not os.path.exists(model_path):
            raise ValueError(f"Local model path '{model_path}' not found.")
        return LocalProvider(model_path=model_path)

    else:
        raise ValueError(f"Unsupported provider: {provider_name}")


# ─────────────────────────────────────────────────────────────────────────────
# Session API endpoints
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/sessions")
async def list_sessions():
    """List all chat sessions (summaries only, newest first)."""
    return {"sessions": _list_sessions()}


@app.post("/api/sessions", status_code=201)
async def create_session(req: SessionCreateRequest):
    """Create a new empty chat session."""
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


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Get full session data including all messages."""
    return _load_session(session_id)


@app.put("/api/sessions/{session_id}")
async def rename_session(session_id: str, req: SessionRenameRequest):
    """Rename an existing chat session."""
    session = _load_session(session_id)
    session["title"] = req.title.strip()[:80]   # cap at 80 chars
    session["updated_at"] = datetime.utcnow().isoformat()
    _save_session(session)
    return {"id": session_id, "title": session["title"]}


@app.delete("/api/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str):
    """Delete a chat session and its message history."""
    path = _session_path(session_id)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    os.remove(path)


# ─────────────────────────────────────────────────────────────────────────────
# Chat endpoint (updated to support sessions)
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Runs the ReAct Agent on the user message and returns the agent reply
    plus telemetry logs. If session_id is provided the messages are persisted.
    """
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # ── Resolve session ──────────────────────────────────────────────────────
    session_id = request.session_id
    session: Optional[Dict[str, Any]] = None

    if session_id:
        try:
            session = _load_session(session_id)
        except HTTPException:
            session_id = None   # Session not found — create a new one below

    if not session_id:
        # Auto-create a session named after the first message
        now = datetime.utcnow().isoformat()
        auto_title = user_message[:50] + ("…" if len(user_message) > 50 else "")
        session = {
            "id": str(uuid.uuid4()),
            "title": auto_title,
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        session_id = session["id"]

    try:
        # 1. Initialize LLM Provider
        provider = get_llm_provider()

        # 2. Register tools
        tools = [
            AnalyzeSymptomTool().to_agent_dict(),
            CheckDoctorAvailabilityTool().to_agent_dict(),
            BookAppointmentTool().to_agent_dict()
        ]

        # 3. Instantiate ReAct Agent
        agent = ReActAgent(llm=provider, tools=tools, max_steps=5)

        # Feed session messages history into agent's conversation history
        if session and "messages" in session:
            history = []
            user_msg = None
            for msg in session["messages"]:
                if msg["role"] == "user":
                    user_msg = msg["content"]
                elif msg["role"] == "agent" and user_msg is not None:
                    history.append({
                        "user": user_msg,
                        "agent": msg["content"]
                    })
                    user_msg = None
            agent.conversation_history = history

        # 4. Capture log file position before running
        log_dir = "logs"
        log_file_path = os.path.join(log_dir, f"{datetime.utcnow().strftime('%Y-%m-%d')}.log")
        start_pos = 0
        if os.path.exists(log_file_path):
            start_pos = os.path.getsize(log_file_path)

        # 5. Run the Agent
        reply = agent.run(user_message)

        # 6. Extract logs generated during this run
        new_logs = []
        if os.path.exists(log_file_path):
            with open(log_file_path, "r", encoding="utf-8") as f:
                f.seek(start_pos)
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            new_logs.append(json.loads(line))
                        except Exception:
                            pass

        # 7. Persist messages into session
        now = datetime.utcnow().isoformat()
        session["messages"].append({
            "role": "user",
            "content": user_message,
            "timestamp": now,
        })
        session["messages"].append({
            "role": "agent",
            "content": reply,
            "timestamp": now,
        })
        session["updated_at"] = now

        # Auto-set title from first user message if still default
        if session["title"] in ("Cuộc trò chuyện mới", "") and user_message:
            session["title"] = user_message[:50] + ("…" if len(user_message) > 50 else "")

        _save_session(session)

        return ChatResponse(reply=reply, logs=new_logs, session_id=session_id)

    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
# Config endpoint
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/api/config")
async def get_config():
    """Returns the configured LLM provider and model name to the frontend."""
    provider_name = os.getenv("DEFAULT_PROVIDER", "google").lower()
    model_name = os.getenv("DEFAULT_MODEL", "gemini-2.5-flash")
    provider_map = {
        "google": "Google Gemini",
        "openai": "OpenAI",
        "local": "Local GGUF"
    }
    return {
        "provider": provider_map.get(provider_name, provider_name.upper()),
        "model": model_name
    }


# Mount static files
os.makedirs("static", exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
