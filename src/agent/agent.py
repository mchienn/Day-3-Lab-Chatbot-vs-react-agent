import os
import re
import time
from typing import List, Dict, Any, Optional, Union
from src.core.llm_provider import LLMProvider
from src.tools.base import BaseTool
from src.telemetry.logger import logger
from src.telemetry.metrics import tracker

# Fallback responses for edge cases
FALLBACK_RESPONSES = {
    "out_of_scope": (
        "Xin lỗi, tôi chỉ hỗ trợ phân luồng bệnh nhân và đặt lịch khám. "
        "Vui lòng mô tả triệu chứng của bạn để tôi tư vấn chuyên khoa phù hợp."
    ),
    "medical_advice": (
        "Tôi không thể tư vấn chẩn đoán hoặc kê đơn thuốc. "
        "Vui lòng đến gặp bác sĩ để được khám và tư vấn trực tiếp. "
        "Tôi có thể giúp bạn đặt lịch khám với chuyên khoa phù hợp."
    ),
    "max_steps": (
        "Tôi đã ghi nhận thông tin của bạn. "
        "Vui lòng cho biết ngày/giờ bạn muốn đặt lịch khám (ví dụ: 'ngày mai', 'thứ 2', '2/6/2026')."
    ),
    "llm_error": (
        "Xin lỗi, hệ thống đang gặp sự cố. Vui lòng thử lại sau."
    ),
    "empty_input": (
        "Vui lòng nhập triệu chứng của bạn để tôi có thể hỗ trợ."
    ),
    "tool_error": (
        "Không thể truy cập thông tin lúc này. Vui lòng thử lại sau."
    )
}


class ReActAgent:
    def __init__(self, llm: LLMProvider, tools: List[Union[BaseTool, Dict[str, Any]]], max_steps: int = 5):
        self.llm = llm
        self.tools = [
            t.to_agent_dict() if isinstance(t, BaseTool) else t
            for t in tools
        ]
        self.max_steps = max_steps
        self.conversation_history = []  # Store user/agent exchanges

    def get_system_prompt(self) -> str:
        tool_descriptions = "\n".join(
            [f"- {t['name']}: {t['description']}" for t in self.tools]
        )

        from datetime import datetime
        now = datetime.now()
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        today_str = f"{now.strftime('%Y-%m-%d')} ({days[now.weekday()]})"

        return f"""You are a smart medical receptionist at a clinic. Your job is to listen to patient symptoms, reason about the correct medical specialty, and help book an appointment.

You have access to the following tools:
{tool_descriptions}

You MUST follow this exact format for every response:

Thought: Analyze the patient's symptoms and decide what to do next.
Action: tool_name("argument")
Observation: (the tool's result will appear here automatically)
... (repeat Thought/Action/Observation as needed)
Final Answer: your final response to the patient.

Rules:
- Always start with a Thought.
- Use exactly ONE Action per step.
- After receiving an Observation, continue with another Thought.
- When you have enough information, give a Final Answer.
- Do NOT invent tool results. Wait for real Observations.
- If a tool returns an error, acknowledge it and try again or ask the patient for clarification.

SYMPTOM ANALYSIS RULES (CRITICAL):
- If the patient mentions ANY symptom, IMMEDIATELY use AnalyzeSymptomTool to identify the specialty.
- Do NOT ask for more details unless the input is completely unrelated to health.
- Examples of CLEAR symptoms that should be processed immediately:
  * "đau bụng, đầy hơi, khó tiêu" → Use AnalyzeSymptomTool
  * "ho, sổ mũi" → Use AnalyzeSymptomTool
  * "đau đầu, chóng mặt" → Use AnalyzeSymptomTool
  * "ngứa, nổi mẩn" → Use AnalyzeSymptomTool
  * "đau lưng" → Use AnalyzeSymptomTool
- Only ask for clarification if the input is truly vague like "tôi không khỏe" or "tôi thấy mệt" with no specific symptoms.
- In your Final Answer to the patient, you MUST clearly state which medical specialty/department you have identified for their symptoms (e.g., "Dựa trên triệu chứng của bạn, tôi đề xuất khám tại Khoa Tiêu hóa. Bạn muốn đặt lịch vào ngày nào ạ?"). Do not omit the department name.

CONTEXT AWARENESS:
- Check the CONVERSATION HISTORY in the prompt carefully.
- If the patient previously mentioned symptoms and now provides a date/time, use the previously identified specialty.
- Today's date is {today_str}. If the patient says "ngày mai" (tomorrow) or mentions other relative dates (e.g. "thứ 3", "ngày kia"), calculate the actual date based on this reference date (e.g. if today is 2026-06-01 (Monday), "ngày mai" is 2026-06-02, "ngày kia" is 2026-06-03, "thứ 4" is 2026-06-03).
- Do NOT ask for symptoms again if already provided in the conversation history.

IMPORTANT CONSTRAINTS:
- You ONLY handle symptom triage and appointment booking.
- Do NOT diagnose diseases or prescribe medication.
- If the patient has already described symptoms in the conversation history, do NOT ask for them again; proceed with appointment booking.
- Avoid repeating the same questions or getting stuck in a loop."""

    def _build_prompt_with_history(self, user_input: str) -> str:
        """Build prompt with conversation history for context awareness."""
        if not self.conversation_history:
            return user_input

        # Build history block
        history_lines = []
        for entry in self.conversation_history[-5:]:  # Last 5 exchanges
            history_lines.append(f"Patient: {entry['user']}")
            # Extract key info from agent response
            agent_resp = entry['agent']
            if 'Khoa' in agent_resp or 'khoa' in agent_resp:
                history_lines.append(f"Agent (identified specialty): {agent_resp}")
            else:
                history_lines.append(f"Agent: {agent_resp}")

        history_text = "\n".join(history_lines)

        return f"""CONVERSATION HISTORY:
{history_text}

CURRENT MESSAGE:
Patient: {user_input}

IMPORTANT: Based on the conversation history above, the patient has already provided symptoms. If they are now providing a date or additional information, use the previously identified specialty to proceed. Do NOT ask for symptoms again."""

    def run(self, user_input: str) -> str:
        # Validate input
        if not user_input or not user_input.strip():
            logger.log_event("AGENT_SKIPPED", {"reason": "empty_input"})
            return FALLBACK_RESPONSES["empty_input"]

        user_input = user_input.strip()

        # Detect obviously out-of-scope input (quick check)
        if self._is_clearly_out_of_scope(user_input):
            logger.log_event("AGENT_SKIPPED", {"reason": "out_of_scope", "input": user_input})
            return FALLBACK_RESPONSES["out_of_scope"]

        session_start = time.time()
        logger.log_event("AGENT_START", {"input": user_input, "model": self.llm.model_name})

        # Build prompt with conversation history for context awareness
        current_prompt = self._build_prompt_with_history(user_input)
        steps = 0
        total_tokens = 0
        total_latency = 0
        last_content = ""

        while steps < self.max_steps:
            step_start = time.time()

            try:
                result = self.llm.generate(current_prompt, system_prompt=self.get_system_prompt())
            except Exception as e:
                logger.log_event("LLM_ERROR", {"step": steps, "error": str(e)})
                self._log_session_summary(user_input, steps, total_tokens, total_latency, session_start, "llm_error")
                return FALLBACK_RESPONSES["llm_error"]

            step_latency = int((time.time() - step_start) * 1000)
            content = result.get("content", "")
            usage = result.get("usage") or {}

            # Handle empty LLM response or API error
            if not content or not content.strip():
                error_msg = result.get("error", "No error message")
                logger.log_event("LLM_EMPTY_RESPONSE", {"step": steps, "error": error_msg, "result": result})
                
                # If the API returned an error, return fallback/rate limit immediately
                if "error" in result:
                    self._log_session_summary(user_input, steps, total_tokens, total_latency, session_start, "llm_error")
                    if "429" in error_msg or "quota" in error_msg.lower():
                        return "Hệ thống đang bận hoặc vượt giới hạn lượt gọi (Rate Limit). Vui lòng đợi vài giây rồi thử lại."
                    return FALLBACK_RESPONSES["llm_error"]

                steps += 1
                continue

            # Track metrics
            tracker.track_request(
                provider=result.get("provider", "unknown"),
                model=self.llm.model_name,
                usage=usage,
                latency_ms=step_latency
            )

            total_tokens += usage.get("total_tokens", 0)
            total_latency += step_latency
            last_content = content

            logger.log_event("LLM_RESPONSE", {
                "step": steps,
                "content": content,
                "usage": usage,
                "latency_ms": step_latency
            })

            # Parse Action (always check for Action first to ensure tools are executed if generated)
            match = re.search(r'Action:\s*(\w+)\((.*?)\)', content)
            if match:
                tool_name = match.group(1)
                tool_args = match.group(2).strip('\'"')
                logger.log_event("TOOL_CALL", {"step": steps, "tool": tool_name, "args": tool_args})
                tracker.track_tool_call(tool_name)

                observation = self._execute_tool(tool_name, tool_args)
                logger.log_event("TOOL_RESULT", {"step": steps, "tool": tool_name, "result": observation})

                current_prompt += f"\n{content}\nObservation: {observation}"
            else:
                # If no Action is present, then check for Final Answer (case-insensitive)
                final_match = re.search(r'(?:Final Answer|Final answer|final answer):\s*(.*)', content, re.DOTALL | re.IGNORECASE)
                if final_match:
                    final = final_match.group(1).strip()
                    if final:
                        # Save to conversation history
                        self.conversation_history.append({
                            "user": user_input,
                            "agent": final
                        })
                        # Keep only last 10 exchanges
                        if len(self.conversation_history) > 10:
                            self.conversation_history = self.conversation_history[-10:]

                        self._log_session_summary(user_input, steps + 1, total_tokens, total_latency, session_start, "final_answer", final)
                        return final

                # No Action and no Final Answer in content.
                # If there's no 'Action:' pattern, the model cannot call a tool. 
                # Instead of looping and hitting rate limits, we treat the content as the Final Answer.
                final = content.strip()
                if final.startswith("Thought:"):
                    # Strip the Thought: prefix if present, but keep the rest
                    final = final.replace("Thought:", "").strip()

                if final:
                    self.conversation_history.append({
                        "user": user_input,
                        "agent": final
                    })
                    if len(self.conversation_history) > 10:
                        self.conversation_history = self.conversation_history[-10:]
                    self._log_session_summary(user_input, steps + 1, total_tokens, total_latency, session_start, "final_answer_fallback", final)
                    return final

                # If content was somehow empty, proceed to format reminder
                current_prompt += f"\n{content}\nPlease follow the format: Thought, Action, or Final Answer."

            steps += 1

        # Max steps reached - try to extract useful info from last response
        logger.log_event("MAX_STEPS_REACHED", {"steps": steps, "last_content": last_content})
        self._log_session_summary(user_input, steps, total_tokens, total_latency, session_start, "max_steps_reached")

        # If last response had a partial answer, use it (case-insensitive)
        final_match = re.search(r'(?:Final Answer|Final answer|final answer):\s*(.*)', last_content, re.DOTALL | re.IGNORECASE)
        if final_match:
            partial = final_match.group(1).strip()
            if partial:
                # Save to conversation history
                self.conversation_history.append({"user": user_input, "agent": partial})
                return partial

        # Save fallback to history
        self.conversation_history.append({"user": user_input, "agent": FALLBACK_RESPONSES["max_steps"]})
        return FALLBACK_RESPONSES["max_steps"]

    def reset_history(self):
        """Clear conversation history (start new patient session)."""
        self.conversation_history = []
        logger.log_event("HISTORY_CLEARED", {})

    def _is_clearly_out_of_scope(self, text: str) -> bool:
        """Quick check for obviously non-medical queries."""
        text_lower = text.lower()

        # Out-of-scope keywords (non-medical topics)
        out_of_scope_keywords = [
            "thời tiết", "weather", "giá vàng", "gold price",
            "bóng đá", "football", "soccer", "game",
            "chứng khoán", "stock", "crypto",
            "nấu ăn", "cooking", "recipe", "công thức",
            "phim", "movie", "film", "nhạc", "music",
            "mua sắm", "shopping", "giảm giá", "discount",
            "lập trình", "programming", "code", "python", "javascript",
            "toán", "math", "vật lý", "physics",
            "chính trị", "politics", "bầu cử", "election"
        ]

        # If text is very short and has no medical keywords, likely out of scope
        if len(text_lower) < 5:
            return False  # Too short to decide, let LLM handle

        # Check for out-of-scope keywords
        for keyword in out_of_scope_keywords:
            if keyword in text_lower:
                # But if also has medical context, let it through
                medical_keywords = ["đau", "buồn nôn", "ho", "sốt", "nhức", "ngứa", "mệt", "khó thở", "chóng mặt"]
                has_medical = any(mk in text_lower for mk in medical_keywords)
                if not has_medical:
                    return True

        return False

    def _log_session_summary(self, user_input: str, steps: int, total_tokens: int, total_latency: int, start_time: float, status: str, final_answer: str = ""):
        session_duration = int((time.time() - start_time) * 1000)
        summary = {
            "input": user_input,
            "steps": steps,
            "total_tokens": total_tokens,
            "total_latency_ms": total_latency,
            "session_duration_ms": session_duration,
            "status": status
        }
        logger.log_event("SESSION_SUMMARY", summary)

        # Export report (keep historical data)
        report_file = tracker.export_report(user_input, final_answer, status)
        logger.log_event("REPORT_SAVED", {"file": report_file})

        # Reset session metrics (historical data preserved)
        tracker.reset_session()

        return summary

    def _execute_tool(self, tool_name: str, args: str) -> str:
        for tool in self.tools:
            if tool['name'] == tool_name:
                func = tool.get('function')
                if func and callable(func):
                    try:
                        return func(args)
                    except Exception as e:
                        logger.log_event("TOOL_ERROR", {"tool": tool_name, "error": str(e)})
                        return f"Error executing {tool_name}: {e}"
                return f"Tool {tool_name} has no function defined."

        # Tool not found - log and return helpful message
        logger.log_event("TOOL_NOT_FOUND", {"tool": tool_name, "available": [t['name'] for t in self.tools]})
        return f"Tool '{tool_name}' không tồn tại. Các tool có sẵn: {', '.join(t['name'] for t in self.tools)}"
