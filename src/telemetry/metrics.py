import os
import json
import time
from datetime import datetime
from typing import Dict, Any, List
from src.telemetry.logger import logger

REPORTS_DIR = "reports"

# Industry pricing (per 1K tokens)
PRICING = {
    "gemini-2.5-flash": {"input": 0.00015, "output": 0.0006},
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "default": {"input": 0.001, "output": 0.002}
}


class PerformanceTracker:
    def __init__(self):
        self.session_metrics = []       # Current session (real-time)
        self.historical_metrics = []    # All sessions (historical)
        self.tool_usage = {}            # Tool call frequency

    def track_request(self, provider: str, model: str, usage: Dict[str, int], latency_ms: int):
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)

        metric = {
            "timestamp": datetime.now().isoformat(),
            "provider": provider,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "latency_ms": latency_ms,
            "cost_estimate": self._calculate_cost(model, prompt_tokens, completion_tokens),
            "tokens_per_second": round(total_tokens / (latency_ms / 1000), 2) if latency_ms > 0 else 0,
            "token_ratio": round(completion_tokens / prompt_tokens, 2) if prompt_tokens > 0 else 0
        }
        self.session_metrics.append(metric)
        logger.log_event("LLM_METRIC", metric)

    def track_tool_call(self, tool_name: str):
        self.tool_usage[tool_name] = self.tool_usage.get(tool_name, 0) + 1

    def _calculate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        pricing = PRICING.get(model, PRICING["default"])
        input_cost = (prompt_tokens / 1000) * pricing["input"]
        output_cost = (completion_tokens / 1000) * pricing["output"]
        return round(input_cost + output_cost, 6)

    def get_summary(self) -> Dict[str, Any]:
        if not self.session_metrics:
            return {"total_requests": 0}

        total_prompt = sum(m["prompt_tokens"] for m in self.session_metrics)
        total_completion = sum(m["completion_tokens"] for m in self.session_metrics)
        total_tokens = sum(m["total_tokens"] for m in self.session_metrics)
        total_latency = sum(m["latency_ms"] for m in self.session_metrics)
        total_cost = sum(m["cost_estimate"] for m in self.session_metrics)
        avg_tps = sum(m["tokens_per_second"] for m in self.session_metrics) / len(self.session_metrics)

        return {
            "total_requests": len(self.session_metrics),
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_tokens,
            "total_latency_ms": total_latency,
            "total_cost_estimate": round(total_cost, 6),
            "avg_latency_ms": total_latency // len(self.session_metrics),
            "avg_tokens_per_request": total_tokens // len(self.session_metrics),
            "avg_tokens_per_second": round(avg_tps, 2),
            "token_ratio": round(total_completion / total_prompt, 2) if total_prompt > 0 else 0,
            "tool_usage": self.tool_usage
        }

    def get_realtime_data(self) -> Dict[str, Any]:
        """Data for real-time dashboard (current session)."""
        return {
            "current_step": len(self.session_metrics),
            "last_metric": self.session_metrics[-1] if self.session_metrics else None,
            "session_summary": self.get_summary(),
            "tool_usage": self.tool_usage
        }

    def get_historical_data(self) -> Dict[str, Any]:
        """Data for historical dashboard (all sessions)."""
        if not self.historical_metrics:
            return {"total_sessions": 0, "sessions": []}

        total_cost = sum(s["cost"] for s in self.historical_metrics)
        total_tokens = sum(s["total_tokens"] for s in self.historical_metrics)
        total_steps = sum(s["steps"] for s in self.historical_metrics)

        return {
            "total_sessions": len(self.historical_metrics),
            "total_cost": round(total_cost, 4),
            "total_tokens": total_tokens,
            "total_steps": total_steps,
            "avg_steps_per_session": round(total_steps / len(self.historical_metrics), 1),
            "sessions": self.historical_metrics
        }

    def get_dashboard_data(self) -> Dict[str, Any]:
        """Combined data for full dashboard."""
        return {
            "realtime": self.get_realtime_data(),
            "historical": self.get_historical_data()
        }

    def export_report(self, user_input: str = "", final_answer: str = "", status: str = "") -> str:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(REPORTS_DIR, f"session_{timestamp}.json")

        summary = self.get_summary()

        report = {
            "timestamp": datetime.now().isoformat(),
            "user_input": user_input,
            "final_answer": final_answer,
            "status": status,
            "summary": summary,
            "details": self.session_metrics
        }

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        # Save to historical
        self.historical_metrics.append({
            "timestamp": datetime.now().isoformat(),
            "user_input": user_input,
            "final_answer": final_answer,
            "status": status,
            "steps": len(self.session_metrics),
            "total_tokens": summary.get("total_tokens", 0),
            "cost": summary.get("total_cost_estimate", 0),
            "latency_ms": summary.get("total_latency_ms", 0)
        })

        logger.log_event("REPORT_EXPORTED", {"file": filename})
        return filename

    def reset_session(self):
        """Reset current session metrics (keep historical)."""
        self.session_metrics = []
        self.tool_usage = {}


# Global tracker instance
tracker = PerformanceTracker()
