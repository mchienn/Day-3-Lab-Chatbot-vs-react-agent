import os
import json
import time
from datetime import datetime
from typing import Dict, Any, List
from src.telemetry.logger import logger

REPORTS_DIR = "reports"

class PerformanceTracker:
    """
    Tracking industry-standard metrics for LLMs.
    """
    def __init__(self):
        self.session_metrics = []

    def track_request(self, provider: str, model: str, usage: Dict[str, int], latency_ms: int):
        """
        Logs a single request metric to our telemetry.
        """
        metric = {
            "provider": provider,
            "model": model,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
            "latency_ms": latency_ms,
            "cost_estimate": self._calculate_cost(model, usage)
        }
        self.session_metrics.append(metric)
        logger.log_event("LLM_METRIC", metric)

    def _calculate_cost(self, model: str, usage: Dict[str, int]) -> float:
        return (usage.get("total_tokens", 0) / 1000) * 0.01

    def get_summary(self) -> Dict[str, Any]:
        if not self.session_metrics:
            return {"total_requests": 0}

        total_tokens = sum(m["total_tokens"] for m in self.session_metrics)
        total_latency = sum(m["latency_ms"] for m in self.session_metrics)
        total_cost = sum(m["cost_estimate"] for m in self.session_metrics)

        return {
            "total_requests": len(self.session_metrics),
            "total_tokens": total_tokens,
            "total_latency_ms": total_latency,
            "total_cost_estimate": round(total_cost, 4),
            "avg_latency_ms": total_latency // len(self.session_metrics),
            "avg_tokens_per_request": total_tokens // len(self.session_metrics)
        }

    def export_report(self, user_input: str = "", final_answer: str = "") -> str:
        os.makedirs(REPORTS_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(REPORTS_DIR, f"session_{timestamp}.json")

        report = {
            "timestamp": datetime.now().isoformat(),
            "user_input": user_input,
            "final_answer": final_answer,
            "summary": self.get_summary(),
            "details": self.session_metrics
        }

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.log_event("REPORT_EXPORTED", {"file": filename})
        return filename

    def reset(self):
        self.session_metrics = []

# Global tracker instance
tracker = PerformanceTracker()
