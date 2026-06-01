# Individual Report: Lab 3 - Chatbot vs ReAct Agent

- **Student Name**: Nguyen Thai Hoc
- **Student ID**: 2A202600909
- **Date**: 01/06/2026

---

## I. Technical Contribution (15 Points)

My specific contribution to the codebase was implementing the core LLM integration layer, specifically the `GeminiProvider` class, to enable the ReAct reasoning loop using Google's Gemini API.

- **Modules Implementated**: `src/core/gemini_provider.py`
- **Code Highlights**:
  ```python
  self.config = genai.GenerationConfig(
      temperature=0.0,
      top_p=0.95,
      top_k=40
  )

Documentation: I configured the GenerationConfig with temperature=0.0 to ensure the agent follows strict, deterministic ReAct logic without hallucinating incorrect tool names or actions. Furthermore, I implemented robust error handling to catch generation_types.StopCandidateException, ensuring that if a user's symptom description triggers safety filters, the agent loop handles it gracefully by returning a structured error message rather than crashing the entire system.

## II. Debugging Case Study (10 Points)

Problem Description: During early testing, the Agent loop occasionally crashed completely when patients described severe or graphic symptoms (e.g., related to injuries). The application threw unhandled exceptions, breaking the ReAct execution.

Log Source: logs/2026-06-01.log (Simulated)

```cmd
[ERROR] Fatal crash in ReAct loop: google.generativeai.types.generation_types.StopCandidateException
```

Diagnosis: The LLM crashed because Gemini's built-in safety filters flagged certain sensitive medical descriptions as harmful content. When the API blocked the content, it raised a StopCandidateException instead of returning a valid Thought or Action, causing our parser to fail.

Solution: I fixed this by wrapping the generate_content execution inside a try-except block specifically targeting generation_types.StopCandidateException. Now, instead of crashing, the code returns {"error": "Content flagged by safety filters.", "content": ""}, allowing the system to inform the patient and safely ask them to rephrase their symptoms.

## III. Personal Insights: Chatbot vs ReAct (10 Points)

- Reasoning: The Thought block was critical for this medical triage use case. Instead of immediately guessing a doctor like a standard chatbot, the agent could reason systematically: "Thought: Patient has severe stomach pain radiating to the back. This relates to Gastroenterology. I need to search the database for Gastroenterologists." This step-by-step thinking prevented the agent from making premature, incorrect bookings.

- Reliability: The Agent actually performed worse than a standard Chatbot in cases of casual conversation or vague inputs (e.g., "Hi, I need help"). The ReAct agent would overthink and try to force these inputs into a tool call (like search_symptoms(query="help")), leading to awkward delays, whereas a Chatbot would just naturally and empathetically ask for more details.

- Observation: Environment feedback was highly effective. If the agent called the tool check_schedule(doctor="Dr. Smith") and received the observation {"status": "fully_booked"}, the agent successfully used that feedback in its next Thought to pivot and search for a different available doctor within the same medical specialty.

## V. Future Improvements (5 Points)

Scalability: Implement an asynchronous message queue (e.g., Redis with Celery) for tool calls. Checking doctor schedules in a real hospital database can take time; async queues will prevent the agent from blocking the main thread while waiting for the database response, allowing the system to handle multiple patients concurrently.

Safety: Implement a "Supervisor" LLM designed to audit the main agent's actions. Before the agent executes a book_appointment action, the Supervisor would review the symptom-to-specialty mapping to ensure no critical medical misdiagnoses occur (e.g., preventing a potential heart attack patient from being routed to a dermatologist).

Performance: Integrate a Vector Database (like Pinecone or ChromaDB) for tool and doctor retrieval. Instead of relying on exact keyword matches for medical specialties, the system could perform semantic searches to match complex patient symptom descriptions with the most relevant doctor profiles and availability.
