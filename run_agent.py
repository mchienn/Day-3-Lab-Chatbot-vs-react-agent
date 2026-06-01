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
from tools import check_red_flags, recommend_specialty, transfer_booking

# --- CONFIGURATION CONSTANTS ---
MAX_ITERATIONS = 5  # Maximum reasoning steps allowed per query
LOG_FILE_PATH = "logs/agent.log"


# --- MOCK LLM PROVIDER FOR FALLBACK/TESTING ---
class MockLLMProvider(LLMProvider):
    """
    Mock LLM Provider that simulates the ReAct reasoning flow
    for testing and educational purposes when API keys are not available.
    """
    def __init__(self, model_name: str = "mock-gemini-2.5"):
        super().__init__(model_name, "mock-api-key")

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        # Count the number of observations to determine the current ReAct loop step
        step = prompt.count("Observation:")
        prompt_lower = prompt.lower()
        
        # Simulate quick API network latency (500ms)
        time.sleep(0.5)
        
        # Check for emergency triggers in the prompt
        is_emergency = any(
            kw in prompt_lower for kw in [
                "đau ngực", "khó thở", "chest pain", "shortness of breath", 
                "stroke", "slurred speech", "bleeding", "unconscious", "seizure"
            ]
        )
        
        content = ""
        if is_emergency:
            if step == 0:
                content = (
                    "Thought: The patient reports symptoms that look like an emergency. I must immediately run check_red_flags.\n"
                    "Action: check_red_flags(\"patient reported emergency symptoms\")"
                )
            elif step == 1:
                content = (
                    "Thought: The check_red_flags tool confirmed an emergency. I must immediately route booking to Cardiology.\n"
                    "Action: transfer_booking(\"Cardiology\")"
                )
            else:
                content = (
                    "Thought: Emergency transfer is done. I will warn the patient and finish.\n"
                    "Final Answer: CANH BAO KHAN CAP: Trieu chung cua ban rat nguy hiem. Chúng tôi đã chuyen tiep ban den khoa Tim mach/Cap cuu. Hay den ngay co so y te gan nhat hoac goi 115!"
                )
        else:
            # Standard Patient Triage Flow
            if step == 0:
                content = (
                    "Thought: I must verify if there are any emergency red flags in the symptoms first.\n"
                    "Action: check_red_flags(\"standard symptoms checking\")"
                )
            elif step == 1:
                content = (
                    "Thought: No emergency red flags found. I will recommend a specialty based on symptoms.\n"
                    "Action: recommend_specialty(\"patient symptoms checking\")"
                )
            elif step == 2:
                # Detect target specialty to mock the reasoning
                specialty = "Gastroenterology"
                if "khớp" in prompt_lower or "xương" in prompt_lower or "ankle" in prompt_lower or "bone" in prompt_lower:
                    specialty = "Orthopedics"
                elif "skin" in prompt_lower or "da" in prompt_lower:
                    specialty = "Dermatology"
                elif "tim" in prompt_lower or "ngực" in prompt_lower:
                    specialty = "Cardiology"
                
                content = (
                    f"Thought: Specialty recommended is {specialty}. I will transfer the patient to the Booking Agent.\n"
                    f"Action: transfer_booking(\"{specialty}\")"
                )
            else:
                specialty = "Gastroenterology"
                if "khớp" in prompt_lower or "xương" in prompt_lower or "ankle" in prompt_lower or "bone" in prompt_lower:
                    specialty = "Orthopedics"
                elif "skin" in prompt_lower or "da" in prompt_lower:
                    specialty = "Dermatology"
                
                content = (
                    f"Thought: Transfer complete. I will inform the patient and close the interaction.\n"
                    f"Final Answer: Tôi đã chuyen thong tin cua ban den Bo phan Dat lich (Booking Agent) cho chuyen khoa {specialty}. Ho se lien he voi ban de sap xep lich hen som nhat."
                )

        return {
            "content": content,
            "usage": {
                "prompt_tokens": 100 + step * 50,
                "completion_tokens": 35,
                "total_tokens": 135 + step * 50
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
                print("\n[TEST] Simulating patient input: 'Tôi đau bụng 2 ngày nay'")
                test_input = "Tôi đau bụng 2 ngày nay"
                run_agent_session(test_input, base_provider)
                
                print("\n[TEST] Simulating patient input: 'Tôi bị đau ngực và khó thở'")
                test_input = "Tôi bị đau ngực và khó thở"
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
    
    # Register and wrap tools with console log interceptors
    registered_tools = [
        {
            "name": "check_red_flags",
            "description": "Checks patient symptoms for life-threatening emergency conditions. Argument: symptoms string.",
            "function": wrap_tool_with_logging("check_red_flags", check_red_flags, steps_tracker)
        },
        {
            "name": "recommend_specialty",
            "description": "Recommends a medical specialty based on patient symptoms. Argument: symptoms string.",
            "function": wrap_tool_with_logging("recommend_specialty", recommend_specialty, steps_tracker)
        },
        {
            "name": "transfer_booking",
            "description": "Transfers patient booking details to the booking agent for the recommended specialty. Argument: specialty name.",
            "function": wrap_tool_with_logging("transfer_booking", transfer_booking, steps_tracker)
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
