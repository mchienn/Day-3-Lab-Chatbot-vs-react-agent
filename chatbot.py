import os
import sys
import json
import time
from typing import Optional, Dict, Any

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

# OpenAI import — chatbot.py uses OpenAI directly (no agent loop)
from openai import OpenAI


# ---------------------------------------------------------------------------
# CHATBOT BASELINE — Phase 2 of the Lab
#
# This is intentionally a SIMPLE chatbot that calls the LLM once without
# any tools or multi-step reasoning. Its purpose is to demonstrate the
# limitations of a plain chatbot when faced with multi-step tasks, which
# motivates the ReAct Agent approach in agent.py.
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are a smart medical receptionist at a clinic. A patient will describe their symptoms.
Your job is to analyze those symptoms and return a structured JSON response.

You MUST respond with ONLY a valid JSON object — no markdown, no extra text.

The JSON must have these exact keys:
- "urgency": one of "Emergency", "High", "Medium", "Low"
- "specialty": the recommended medical specialty (e.g. "Cardiology", "General Practice"), or "None" if unclear
- "confidence": a float between 0.0 and 1.0 representing your confidence
- "next_step": one of "BookingAgent", "Clarify", "EmergencyService"

Example output:
{"urgency": "High", "specialty": "Cardiology", "confidence": 0.9, "next_step": "BookingAgent"}
"""


def triage_patient(symptoms_text: str) -> Dict[str, Any]:
    """
    Chatbot Baseline: calls the LLM once (no tools, no agent loop) to
    analyze a patient's symptoms and return a structured triage result.

    This represents the Phase 2 "Chatbot" that students compare against
    the full ReAct Agent. Unlike the agent, this function cannot perform
    multi-step reasoning or tool calls — it relies entirely on the LLM's
    internal knowledge.

    Args:
        symptoms_text: Plain text describing the patient's symptoms.

    Returns:
        Dict containing:
          - urgency (str): Emergency / High / Medium / Low
          - specialty (str): Recommended specialty or "None"
          - confidence (float): 0.0 – 1.0
          - next_step (str): BookingAgent / Clarify / EmergencyService
          - _meta (dict): token usage statistics
          - error (str, optional): present only if JSON parsing failed
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_openai_api_key_here":
        raise ValueError("OPENAI_API_KEY is not set in .env")

    client = OpenAI(api_key=api_key)
    model_name = os.getenv("DEFAULT_MODEL", "gpt-4o")

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": symptoms_text},
        ],
        temperature=0.0,
    )

    raw_content = response.choices[0].message.content or ""
    usage = response.usage

    meta = {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
    }

    # Attempt to parse the JSON output from the LLM
    try:
        # Strip markdown code fences if LLM includes them despite instructions
        cleaned = raw_content.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("```")[1]
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()

        result = json.loads(cleaned)
        result["_meta"] = meta
        return result

    except (json.JSONDecodeError, ValueError):
        # Graceful fallback — the guide covers this pitfall explicitly
        return {
            "urgency": "Low",
            "specialty": "None",
            "confidence": 0.0,
            "next_step": "Clarify",
            "error": f"Failed to parse LLM response as JSON. Raw: {raw_content[:200]}",
            "_meta": meta,
        }


# ---------------------------------------------------------------------------
# Interactive CLI — for manual testing during lab Phase 2
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  Vinmec Medical Triage — CHATBOT BASELINE (Phase 2)")
    print("  (No tools, no agent loop — single LLM call only)")
    print("=" * 60)

    try:
        # Quick connection check
        triage_patient("test")
    except ValueError as e:
        print(f"[ERROR] {e}")
        print("Please configure .env with a valid OPENAI_API_KEY.")
        return

    print("\nDescribe your symptoms below, or type 'exit' to quit.")
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
            result = triage_patient(user_input)
            duration = time.time() - start

            print(f"\nTriage Result:")
            print(f"  Urgency   : {result.get('urgency')}")
            print(f"  Specialty : {result.get('specialty')}")
            print(f"  Confidence: {result.get('confidence')}")
            print(f"  Next Step : {result.get('next_step')}")
            if "error" in result:
                print(f"  ⚠ Parse Error: {result['error']}")
            meta = result.get("_meta", {})
            print(f"  Tokens    : {meta.get('total_tokens')} total  [{duration:.1f}s]")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"[ERROR] {e}")


if __name__ == "__main__":
    main()
