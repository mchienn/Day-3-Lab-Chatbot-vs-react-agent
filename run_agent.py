import os
import sys
import re
import time
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Generator

# Enable UTF-8 encoding or fallback replacement on Windows to prevent UnicodeEncodeError
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        try:
            sys.stdout.reconfigure(errors="replace")
            sys.stderr.reconfigure(errors="replace")
        except Exception:
            pass

# Add the current directory to sys.path to allow running from anywhere in the workspace
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Load dotenv to read configured keys and model names
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Core system imports
from src.core.llm_provider import LLMProvider
from src.agent.agent import ReActAgent
from src.tools.medical_tools import (
    AnalyzeSymptomTool,
    CheckDoctorAvailabilityTool,
    BookAppointmentTool
)

# --- CONFIGURATION CONSTANTS ---
MAX_ITERATIONS = 5  # Maximum reasoning steps allowed per query
LOG_FILE_PATH = "logs/agent.log"


# --- MOCK LLM PROVIDER FOR FALLBACK/TESTING ---
class MockLLMProvider(LLMProvider):
    """
    Mock LLM Provider that simulates the ReAct reasoning flow using the official
    AnalyzeSymptomTool, CheckDoctorAvailabilityTool, and BookAppointmentTool.
    """
    def __init__(self, model_name: str = "mock-gemini-2.5"):
        super().__init__(model_name, "mock-api-key")

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        # Count the number of observations to determine the current ReAct loop step
        step = prompt.count("Observation:")
        time.sleep(0.5)  # Simulate network latency
        
        content = ""
        if step == 0:
            content = (
                "Thought: The patient wants to book an appointment for stomach pain. I need to first analyze their symptoms to recommend a specialty.\n"
                "Action: AnalyzeSymptomTool(\"Tôi bị đau bụng nhiều và đầy hơi khó tiêu\")"
            )
        elif step == 1:
            content = (
                "Thought: The specialty recommended is 'Khoa Tiêu hóa'. I should check the available time slots for doctors in this specialty on 2026-06-02.\n"
                "Action: CheckDoctorAvailabilityTool(\"Khoa Tiêu hóa\", \"2026-06-02\")"
            )
        elif step == 2:
            content = (
                "Thought: I see BS. Trần Văn A has available slots in the morning. I will book an appointment for the patient 'Nguyễn Văn A' at 08:00.\n"
                "Action: BookAppointmentTool(\"Nguyễn Văn A\", \"BS. Trần Văn A\", \"2026-06-02 08:00\")"
            )
        else:
            content = (
                "Thought: The booking is confirmed. I will give the patient their booking details and reference code.\n"
                "Final Answer: Tôi đã đặt lịch thành công cho bạn Nguyễn Văn A với BS. Trần Văn A vào lúc 08:00 ngày 2026-06-02. Mã cuộc hẹn của bạn là TK-8699."
            )

        return {
            "content": content,
            "usage": {
                "prompt_tokens": 100 + step * 50,
                "completion_tokens": 40,
                "total_tokens": 140 + step * 50
            },
            "latency_ms": 500,
            "provider": "mock"
        }

    def stream(self, prompt: str, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        res = self.generate(prompt, system_prompt)
        yield res["content"]


# --- INTERCEPTOR PROVIDER WRAPPER FOR CONSOLE DISPLAY & TRACING ---
class LoggedProviderWrapper(LLMProvider):
    """
    Wraps any LLMProvider to capture and display reasoning steps (Thoughts, Actions,
    Final Answers) in real-time on the console, and trace them for agent.log.
    """
    def __init__(self, base_provider: LLMProvider, steps_tracker: list):
        super().__init__(base_provider.model_name, base_provider.api_key)
        self.base_provider = base_provider
        self.steps_tracker = steps_tracker

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        try:
            # Call the wrapped provider
            result = self.base_provider.generate(prompt, system_prompt)
            if "error" in result:
                raise RuntimeError(result["error"])
        except Exception as e:
            # Handle provider failure gracefully
            print(f"\n[ERROR] LLM Provider connection failed: {e}")
            error_response = {
                "content": f"Thought: The LLM Provider is failing due to error: {e}. I must stop and inform the patient.\nFinal Answer: Rất tiếc, hệ thống đang gặp sự cố kết nối. Vui lòng thử lại sau.",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "latency_ms": 0,
                "provider": "failed"
            }
            result = error_response

        content = result.get("content", "")
        
        # Parse Thought
        thought = "No thought found."
        thought_match = re.search(r'Thought:\s*(.*?)(?=(?:Action:|Final Answer:|$))', content, re.DOTALL)
        if thought_match:
            thought = thought_match.group(1).strip()
            
        # Parse Action or Final Answer
        action = None
        final_answer = None
        
        action_match = re.search(r'Action:\s*(\w+)\((.*?)\)', content)
        if action_match:
            action = f"{action_match.group(1)}({action_match.group(2)})"
        elif "Final Answer:" in content:
            final_answer = content.split("Final Answer:")[-1].strip()

        # Track the step
        self.steps_tracker.append({
            "step_index": len(self.steps_tracker) + 1,
            "thought": thought,
            "action": action,
            "observation": None,
            "final_answer": final_answer,
            "usage": result.get("usage", {}),
            "latency_ms": result.get("latency_ms", 0),
            "provider": result.get("provider", "unknown")
        })

        # Print to console in real-time
        print(f"\n[Thought]: {thought}")
        if action:
            print(f"[Action]: Executing {action}...")
        elif final_answer:
            print(f"[Final Answer]: {final_answer}")
            
        return result

    def stream(self, prompt: str, system_prompt: Optional[str] = None) -> Generator[str, None, None]:
        return self.base_provider.stream(prompt, system_prompt)


# --- CONSOLE OBSERVATION LOGGER FOR TOOLS ---
def wrap_tool_with_logging(tool_name: str, tool_func, steps_tracker: list):
    """
    Wraps a tool function to print its observation result to the console
    and append the observation data to the active step trace in steps_tracker.
    """
    def logged_tool_runner(args: str) -> str:
        try:
            observation = tool_func(args)
        except Exception as e:
            observation = f"Error executing {tool_name}: {str(e)}"
            
        print(f"[Observation]: {observation}")
        
        # Store observation in the last tracked step
        if steps_tracker:
            steps_tracker[-1]["observation"] = observation
            
        return observation
    return logged_tool_runner


# --- INTERACTION LOGGER TO logs/agent.log ---
def write_interaction_log(user_input: str, steps: list, final_response: str):
    """
    Writes a structured, academic-grade record of the entire interaction session
    to logs/agent.log. Includes timestamp, step details, and total metrics.
    """
    try:
        os.makedirs(os.path.dirname(LOG_FILE_PATH), exist_ok=True)
        
        # Calculate totals for performance analysis
        total_latency = sum(step.get("latency_ms", 0) for step in steps)
        total_prompt_tokens = sum(step.get("usage", {}).get("prompt_tokens", 0) for step in steps)
        total_completion_tokens = sum(step.get("usage", {}).get("completion_tokens", 0) for step in steps)
        total_tokens = sum(step.get("usage", {}).get("total_tokens", 0) for step in steps)
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "user_input": user_input,
            "steps": [
                {
                    "step": s["step_index"],
                    "thought": s["thought"],
                    "action": s["action"],
                    "observation": s["observation"]
                }
                for s in steps
            ],
            "final_response": final_response,
            "metrics": {
                "total_steps": len(steps),
                "total_latency_ms": total_latency,
                "total_prompt_tokens": total_prompt_tokens,
                "total_completion_tokens": total_completion_tokens,
                "total_tokens": total_tokens
            }
        }
        
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            
    except Exception as e:
        print(f"[ERROR] Failed to write to {LOG_FILE_PATH}: {e}")


# --- PROVIDER INITIALIZATION & FACTORY ---
def initialize_provider() -> LLMProvider:
    """
    Factory function to initialize the LLM Provider based on environmental config.
    Checks API keys and falls back to MockLLMProvider if keys are placeholders or missing.
    """
    provider_name = os.getenv("DEFAULT_PROVIDER", "google").lower()
    
    if provider_name == "google":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or api_key == "your_gemini_api_key_here":
            print("[INFO] No valid GEMINI_API_KEY found in .env. Initializing MockLLMProvider.")
            return MockLLMProvider()
        try:
            from src.core.gemini_provider import GeminiProvider
            model_name = os.getenv("DEFAULT_MODEL", "gemini-2.5-flash")
            print(f"[INFO] Initializing GeminiProvider with model: {model_name}")
            return GeminiProvider(model_name=model_name, api_key=api_key)
        except Exception as e:
            print(f"[WARNING] Failed to load GeminiProvider: {e}. Falling back to MockLLMProvider.")
            return MockLLMProvider()
            
    elif provider_name == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "your_openai_api_key_here":
            print("[INFO] No valid OPENAI_API_KEY found in .env. Initializing MockLLMProvider.")
            return MockLLMProvider()
        try:
            from src.core.openai_provider import OpenAIProvider
            model_name = os.getenv("DEFAULT_MODEL", "gpt-4o")
            print(f"[INFO] Initializing OpenAIProvider with model: {model_name}")
            return OpenAIProvider(model_name=model_name, api_key=api_key)
        except Exception as e:
            print(f"[WARNING] Failed to load OpenAIProvider: {e}. Falling back to MockLLMProvider.")
            return MockLLMProvider()
            
    else:
        print(f"[INFO] Provider '{provider_name}' not recognized. Initializing MockLLMProvider.")
        return MockLLMProvider()


# --- MAIN RUNNER CLI ---
def main():
    print("==================================================")
    print("=== Vinmec Smart Receptionist Agent (ReAct Run) ===")
    print("==================================================")
    
    # Initialize the LLM Provider
    base_provider = initialize_provider()
    
    print("\n--- CLI chat loop started ---")
    print("Type 'exit' or 'quit' to end the session.")
    print("Type 'test' to run automated mock scenario tests.")
    print("="*50)
    
    while True:
        try:
            user_input = input("\nPatient: ").strip()
            if not user_input:
                continue
                
            if user_input.lower() in ["exit", "quit"]:
                print("Exiting ReAct Agent session. Goodbye!")
                break
                
            # Quick trigger for running mock tests if input is 'test'
            if user_input.lower() == "test":
                print("\n[TEST] Simulating patient input: 'Tôi bị đau bụng nhiều và đầy hơi khó tiêu'")
                test_input = "Tôi bị đau bụng nhiều và đầy hơi khó tiêu"
                run_agent_session(test_input, base_provider)
                continue
                
            run_agent_session(user_input, base_provider)
            
        except KeyboardInterrupt:
            print("\nExiting ReAct Agent session. Goodbye!")
            break
        except Exception as e:
            print(f"[ERROR] Session execution crashed: {e}")


def run_agent_session(user_input: str, base_provider: LLMProvider):
    """
    Runs a single query interaction through the ReActAgent, captures logs,
    and displays intermediate trace logs and final response.
    """
    # Steps tracker list specifically instantiated for this session
    steps_tracker = []
    
    # Wrap provider to capture and log completions in real-time
    logged_provider = LoggedProviderWrapper(base_provider, steps_tracker)
    
    # Instantiate the new official medical tools
    symptom_tool = AnalyzeSymptomTool()
    availability_tool = CheckDoctorAvailabilityTool()
    booking_tool = BookAppointmentTool()
    
    # Register and wrap official tools with console log interceptors
    registered_tools = [
        {
            "name": symptom_tool.name,
            "description": symptom_tool.description,
            "function": wrap_tool_with_logging(symptom_tool.name, symptom_tool.execute_from_string, steps_tracker)
        },
        {
            "name": availability_tool.name,
            "description": availability_tool.description,
            "function": wrap_tool_with_logging(availability_tool.name, availability_tool.execute_from_string, steps_tracker)
        },
        {
            "name": booking_tool.name,
            "description": booking_tool.description,
            "function": wrap_tool_with_logging(booking_tool.name, booking_tool.execute_from_string, steps_tracker)
        }
    ]
    
    # Instantiate the ReAct agent
    agent = ReActAgent(
        llm=logged_provider,
        tools=registered_tools,
        max_steps=MAX_ITERATIONS
    )
    
    print("\n--- Agent reasoning in progress ---")
    start_time = time.time()
    
    try:
        final_answer = agent.run(user_input)
    except Exception as e:
        print(f"\n[ERROR] Agent failed to execute: {e}")
        final_answer = "Rất tiếc, hệ thống gặp sự cố trong quá trình xử lý triệu chứng."
        
    duration = time.time() - start_time
    
    # Visual separation in console
    print("\n" + "-"*50)
    print(f"Agent Response: {final_answer}")
    print(f"Metrics: {len(steps_tracker)} steps | {duration:.2f}s total latency")
    print("-"*50)
    
    # Log the interaction session to logs/agent.log
    write_interaction_log(user_input, steps_tracker, final_answer)


if __name__ == "__main__":
    main()
