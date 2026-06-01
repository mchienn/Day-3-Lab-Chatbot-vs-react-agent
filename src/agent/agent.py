import os
import re
from typing import List, Dict, Any, Optional
from src.core.llm_provider import LLMProvider
from src.telemetry.logger import logger

class ReActAgent:
    """
    SKELETON: A ReAct-style Agent that follows the Thought-Action-Observation loop.
    Students should implement the core loop logic and tool execution.
    """
    
    def __init__(self, llm: LLMProvider, tools: List[Dict[str, Any]], max_steps: int = 5):
        self.llm = llm
        self.tools = tools
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
        logger.log_event("AGENT_START", {"input": user_input, "model": self.llm.model_name})

        current_prompt = user_input
        steps = 0

        while steps < self.max_steps:
            result = self.llm.generate(current_prompt, system_prompt=self.get_system_prompt())
            content = result["content"]
            logger.log_event("LLM_RESPONSE", {"step": steps, "content": content, "usage": result.get("usage")})

            # Check for Final Answer
            if "Final Answer:" in content:
                final = content.split("Final Answer:")[-1].strip()
                logger.log_event("AGENT_END", {"steps": steps + 1, "status": "final_answer"})
                return final

            # Parse Action
            match = re.search(r'Action:\s*(\w+)\((.*?)\)', content)
            if match:
                tool_name = match.group(1)
                tool_args = match.group(2).strip('\'"')
                logger.log_event("TOOL_CALL", {"step": steps, "tool": tool_name, "args": tool_args})

                observation = self._execute_tool(tool_name, tool_args)
                logger.log_event("TOOL_RESULT", {"step": steps, "tool": tool_name, "result": observation})

                current_prompt += f"\n{content}\nObservation: {observation}"
            else:
                # No Action and no Final Answer — ask LLM to follow format
                current_prompt += f"\n{content}\nPlease follow the format: Thought, Action, or Final Answer."

            steps += 1

        logger.log_event("AGENT_END", {"steps": steps, "status": "max_steps_reached"})
        return "Agent stopped: maximum steps reached without a final answer."

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
