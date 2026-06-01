import os
import json
import re
import sys
from typing import Dict, Any, Optional
from openai import OpenAI

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

# Try to load environment variables from a .env file if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# --- SYSTEM PROMPT ---
SYSTEM_PROMPT = """You are the Vinmec Triage Agent, an initial patient triage assistant at Vinmec International Hospital.
Your role is to perform initial patient triage before booking appointments.

### Goals:
1. Collect and analyze patient symptoms.
2. Recommend a medical specialty (e.g., Cardiology, Neurology, Gastroenterology, Pediatrics, Orthopedics, Pulmonology, Dermatology, General Medicine, ENT, etc.).
3. Detect emergency conditions immediately.
4. Transfer the patient to the Booking Agent when enough information is collected or if there is an emergency.

### Emergency Conditions to Detect:
- Chest pain with shortness of breath
- Stroke symptoms (e.g., facial drooping, arm weakness, slurred speech)
- Severe bleeding
- Loss of consciousness
- Seizures

### Strict Constraints:
- Do NOT diagnose specific diseases (e.g., do NOT tell the patient they have a "heart attack", "stroke", "appendicitis", "COVID-19", etc. Recommend the specialty, not the disease).
- Do NOT prescribe or suggest medications (e.g., do NOT tell them to take aspirin, paracetamol, antibiotics, etc.).
- Do NOT replace doctors. Keep advice general, emphasizing that this is a triage routing, not a medical diagnosis.

### Output Format:
You must reply ONLY with a valid JSON object matching this schema. Do not output any thinking or markdown code block formatting (like ```json ... ```). Output the raw JSON directly:
{
  "urgency": "Emergency" | "High" | "Medium" | "Low",
  "specialty": "<Recommended Medical Specialty or 'None' if unclear>",
  "confidence": <float value between 0.0 and 1.0 representing confidence in the triage/specialty>,
  "next_step": "BookingAgent" | "Clarify"
}

Guidance for fields:
- If an emergency condition is detected: Set "urgency" to "Emergency", "next_step" to "BookingAgent", and select the most appropriate specialty (e.g., "Cardiology", "Neurology", "General Medicine").
- If the patient's symptoms are clear and triage is successful: Set "urgency" to "High", "Medium", or "Low", set "specialty" to the appropriate department, and set "next_step" to "BookingAgent".
- If the symptoms are too vague or insufficient to make a recommendation: Set "specialty" to "None", "confidence" to 0.0, and "next_step" to "Clarify".
"""

def triage_patient(symptoms: str, api_key: Optional[str] = None, model: Optional[str] = None) -> Dict[str, Any]:
    """
    Triage patient symptoms using the OpenAI API.
    
    Args:
        symptoms (str): Symptoms described by the patient.
        api_key (str, optional): The OpenAI API key. Defaults to environmental variable.
        model (str, optional): OpenAI model name. Defaults to DEFAULT_MODEL env var or gpt-4o.
        
    Returns:
        Dict[str, Any]: Parsed JSON response containing urgency, specialty, confidence, and next_step.
    """
    # Fetch configurations from environment if not explicitly passed
    actual_api_key = api_key or os.getenv("OPENAI_API_KEY")
    actual_model = model or os.getenv("DEFAULT_MODEL", "gpt-4o")
    
    if not actual_api_key:
        raise ValueError(
            "OpenAI API Key not found. Please set the OPENAI_API_KEY environment variable "
            "or create a .env file with your key."
        )

    # Initialize client
    client = OpenAI(api_key=actual_api_key)
    
    try:
        # Request completion
        response = client.chat.completions.create(
            model=actual_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": symptoms}
            ],
            response_format={"type": "json_object"},
            temperature=0.0  # Keep triage deterministic
        )
        
        raw_content = response.choices[0].message.content.strip()
        
        # Clean potential markdown wrapping (just in case, though response_format="json_object" is used)
        cleaned_content = re.sub(r"^```json\s*", "", raw_content, flags=re.IGNORECASE)
        cleaned_content = re.sub(r"\s*```$", "", cleaned_content)
        
        parsed_response = json.loads(cleaned_content)
        
        # Ensure all required keys exist
        required_keys = ["urgency", "specialty", "confidence", "next_step"]
        for key in required_keys:
            if key not in parsed_response:
                parsed_response[key] = "None" if key != "confidence" else 0.0
                
        # Inject token usage and latency for educational/metric analysis in the lab
        parsed_response["_meta"] = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
            "model": actual_model
        }
        
        return parsed_response

    except json.JSONDecodeError as e:
        print(f"JSON parsing error: {e}")
        return {
            "urgency": "Medium",
            "specialty": "General Medicine",
            "confidence": 0.0,
            "next_step": "Clarify",
            "error": "Failed to parse JSON response from LLM"
        }
    except Exception as e:
        print(f"API execution error: {e}")
        return {
            "urgency": "Medium",
            "specialty": "General Medicine",
            "confidence": 0.0,
            "next_step": "Clarify",
            "error": str(e)
        }

def run_tests():
    """Runs a suite of test cases to verify chatbot performance against requirements."""
    test_cases = [
        {
            "name": "Emergency 1 - Chest Pain",
            "input": "I have sudden chest pain that spreads to my shoulder, and I am gasping for air. It's hard to breathe."
        },
        {
            "name": "Emergency 2 - Stroke",
            "input": "My grandmother suddenly can't move the left side of her face and her speech is very slurred."
        },
        {
            "name": "Non-Emergency - Orthopedics",
            "input": "I twisted my ankle playing basketball yesterday. It is swollen and sore, but I can still limp around."
        },
        {
            "name": "Non-Emergency - Gastroenterology",
            "input": "I have had a mild stomach ache and bloating since eating seafood last night."
        },
        {
            "name": "Vague Input - Clarification Needed",
            "input": "Hi, I'm feeling a bit unwell today."
        }
    ]
    
    print("\n" + "="*50)
    print("[START] RUNNING AUTOMATED TRIAGE TEST CASES")
    print("="*50)
    
    for tc in test_cases:
        print(f"\n[Test Case]: {tc['name']}")
        print(f"Patient Input: \"{tc['input']}\"")
        try:
            result = triage_patient(tc["input"])
            print("Response JSON:")
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(f"[ERROR] Test failed with error: {e}")
            
    print("\n" + "="*50)
    print("[END] TEST RUN COMPLETED")
    print("="*50 + "\n")

def main():
    print("=== Vinmec Triage Chatbot Baseline ===")
    print("Initializing...")
    
    # Check if OPENAI_API_KEY is available
    if not os.getenv("OPENAI_API_KEY"):
        print("[WARNING] OPENAI_API_KEY environment variable is not set.")
        print("Please check your .env file or export the variable before running.")
        return
        
    print(f"Using default model: {os.getenv('DEFAULT_MODEL', 'gpt-4o')}")
    
    # Ask if user wants to run automated tests or start interactive mode
    print("\nSelect mode:")
    print("1. Run automated test suite")
    print("2. Start interactive terminal chat")
    
    choice = input("Enter option (1 or 2): ").strip()
    
    if choice == "1":
        run_tests()
    elif choice == "2":
        print("\n" + "="*50)
        print("--- Interactive Triage Chat started ---")
        print("Type 'exit' or 'quit' to stop.")
        print("="*50)
        
        while True:
            try:
                user_input = input("\nPatient: ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ["exit", "quit"]:
                    print("Exiting triage chat. Goodbye!")
                    break
                    
                result = triage_patient(user_input)
                print("Triage Agent:")
                print(json.dumps(result, indent=2))
                
                # Check for emergency warning
                if result.get("urgency") == "Emergency":
                    print("\n[ALERT] EMERGENCY CONDITION DETECTED! Routing immediately to emergency services.")
                elif result.get("next_step") == "BookingAgent":
                    print(f"\n[BOOKING] Routing patient to Booking Agent for specialty: {result.get('specialty')}")
                else:
                    print("\n[CLARIFY] Patient details unclear. Asking for clarification.")
                    
            except KeyboardInterrupt:
                print("\nExiting triage chat. Goodbye!")
                break
            except Exception as e:
                print(f"Error: {e}")
    else:
        print("Invalid choice. Running automated tests by default...")
        run_tests()

if __name__ == "__main__":
    main()
