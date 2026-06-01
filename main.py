import warnings
# Suppress Google API version and package deprecation warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

import os
import json
from datetime import datetime
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import core modules
from src.core.openai_provider import OpenAIProvider
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

app = FastAPI(title="Smart Medical Triage & Booking AI Agent")

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str
    logs: List[Dict[str, Any]]

def get_llm_provider():
    """
    Instantiates the LLM provider configured in the .env file.
    """
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
            raise ValueError("Local provider requires 'llama-cpp-python' package which is not installed or failed to import.")
        model_path = os.getenv("LOCAL_MODEL_PATH")
        if not model_path or not os.path.exists(model_path):
            raise ValueError(f"Local model path '{model_path}' not found. Please download the GGUF model first.")
        return LocalProvider(model_path=model_path)
        
    else:
        raise ValueError(f"Unsupported provider: {provider_name}")

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Exposes a chat endpoint to run the ReAct Agent on the user message
    and returns both the agent reply and the generated telemetry logs.
    """
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        # 1. Initialize LLM Provider
        provider = get_llm_provider()

        # 2. Register tools
        tools = [
            AnalyzeSymptomTool().to_agent_dict(),
            CheckDoctorAvailabilityTool().to_agent_dict(),
            BookAppointmentTool().to_agent_dict()
        ]

        # 3. Instantiate ReAct Agent (limit to 5 steps max to prevent infinite loops)
        agent = ReActAgent(llm=provider, tools=tools, max_steps=5)

        # 4. Prepare log file tracking to capture events in real time
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

        return ChatResponse(reply=reply, logs=new_logs)

    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

@app.get("/api/config")
async def get_config():
    """
    Returns the configured LLM provider and model name to the frontend.
    """
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

# Mount static files to serve the HTML/CSS/JS frontend
# Make sure static directory exists
os.makedirs("static", exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    # Start server on local port 8000
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
