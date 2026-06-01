import os
import sys
import time
from typing import Optional

# Windows UTF-8 support
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

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Core imports
from src.core.llm_provider import LLMProvider
from src.agent.agent import ReActAgent
from src.tools.medical_tools import (
    AnalyzeSymptomTool,
    CheckDoctorAvailabilityTool,
    BookAppointmentTool,
)


def create_provider() -> LLMProvider:
    """Create LLM provider based on .env config."""
    provider_name = os.getenv("DEFAULT_PROVIDER", "google").lower()

    if provider_name == "google":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or api_key == "your_gemini_api_key_here":
            raise ValueError("GEMINI_API_KEY not set in .env")
        from src.core.gemini_provider import GeminiProvider
        model_name = os.getenv("DEFAULT_MODEL", "gemini-2.5-flash")
        print(f"[INFO] Using GeminiProvider ({model_name})")
        return GeminiProvider(model_name=model_name, api_key=api_key)

    elif provider_name == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key == "your_openai_api_key_here":
            raise ValueError("OPENAI_API_KEY not set in .env")
        from src.core.openai_provider import OpenAIProvider
        model_name = os.getenv("DEFAULT_MODEL", "gpt-4o")
        print(f"[INFO] Using OpenAIProvider ({model_name})")
        return OpenAIProvider(model_name=model_name, api_key=api_key)

    else:
        raise ValueError(f"Unknown provider: {provider_name}")


def create_agent(llm: LLMProvider) -> ReActAgent:
    """Create ReActAgent with medical tools."""
    tools = [
        AnalyzeSymptomTool(),
        CheckDoctorAvailabilityTool(),
        BookAppointmentTool(),
    ]
    return ReActAgent(llm=llm, tools=tools, max_steps=5)


def main():
    print("=" * 60)
    print("Vinmec Smart Receptionist Agent")
    print("=" * 60)

    try:
        llm = create_provider()
    except ValueError as e:
        print(f"[ERROR] {e}")
        print("Please configure .env with valid API key.")
        return

    agent = create_agent(llm)

    print("\nType your symptoms or 'exit' to quit.")
    print("=" * 60)

    while True:
        try:
            user_input = input("\nPatient: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit"]:
                print("Goodbye!")
                break

            start = time.time()
            result = agent.run(user_input)
            duration = time.time() - start

            print(f"\nAgent: {result}")
            print(f"[{duration:.1f}s]")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"[ERROR] {e}")


if __name__ == "__main__":
    main()
