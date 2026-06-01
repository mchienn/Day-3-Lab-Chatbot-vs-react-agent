import os
import re
import time
from typing import List, Dict, Any, Optional, Union
from src.core.llm_provider import LLMProvider
from src.tools.base import BaseTool
from src.telemetry.logger import logger
from src.telemetry.metrics import tracker

class ReActAgent:
    def __init__(self, llm: LLMProvider, tools: List[Union[BaseTool, Dict[str, Any]]], max_steps: int = 5):
        self.llm = llm
        self.tools = [
            t.to_agent_dict() if isinstance(t, BaseTool) else t
            for t in tools
        ]
        self.max_steps = max_steps
        self.history = []

    def get_system_prompt(self) -> str:
        tool_descriptions = "\n".join(
            [f"- {t['name']}: {t['description']}" for t in self.tools]
        )
        return f"""
You are a smart medical receptionist at a clinic. Your job is to listen to patient symptoms, reason about the correct medical specialty, and help book an appointment.

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
- If a tool returns an error, acknowledge it and try again or ask the patient for clarification."""

    def run(self, user_input: str) -> str:
        session_start = time.time()
        logger.log_event("AGENT_START", {"input": user_input, "model": self.llm.model_name})

        current_prompt = user_input
        steps = 0
        total_tokens = 0
        total_latency = 0

        while steps < self.max_steps:
            step_start = time.time()
            result = self.llm.generate(current_prompt, system_prompt=self.get_system_prompt())
            step_latency = int((time.time() - step_start) * 1000)

            content = result["content"]
            usage = result.get("usage") or {}

            # Track metrics
            tracker.track_request(
                provider=result.get("provider", "unknown"),
                model=self.llm.model_name,
                usage=usage,
                latency_ms=step_latency
            )

            total_tokens += usage.get("total_tokens", 0)
            total_latency += step_latency

            logger.log_event("LLM_RESPONSE", {
                "step": steps,
                "content": content,
                "usage": usage,
                "latency_ms": step_latency
            })

            # Check for Final Answer
            if "Final Answer:" in content:
                final = content.split("Final Answer:")[-1].strip()
                self._log_session_summary(user_input, steps + 1, total_tokens, total_latency, session_start, "final_answer", final)
                return final

            # Parse Action
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
                current_prompt += f"\n{content}\nPlease follow the format: Thought, Action, or Final Answer."

            steps += 1

        self._log_session_summary(user_input, steps, total_tokens, total_latency, session_start, "max_steps_reached")
        return "Agent stopped: maximum steps reached without a final answer."

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
                        return f"Error executing {tool_name}: {e}"
                return f"Tool {tool_name} has no function defined."
        return f"Tool {tool_name} not found."
