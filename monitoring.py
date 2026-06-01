import os
import json
import glob
from datetime import datetime
from typing import List, Dict, Any
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Agent Monitoring Dashboard")

REPORTS_DIR = "reports"
LOGS_DIR = "logs"


def _get_reports() -> List[Dict[str, Any]]:
    """Read all report files from reports/ directory."""
    reports = []
    pattern = os.path.join(REPORTS_DIR, "session_*.json")
    for filepath in sorted(glob.glob(pattern), reverse=True):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            reports.append({
                "filename": os.path.basename(filepath),
                "timestamp": data.get("timestamp", ""),
                "user_input": data.get("user_input", "")[:80],
                "status": data.get("status", ""),
                "summary": data.get("summary", {}),
            })
        except Exception:
            pass
    return reports


def _get_report_detail(filename: str) -> Dict[str, Any]:
    """Read a specific report file."""
    filepath = os.path.join(REPORTS_DIR, filename)
    if not os.path.exists(filepath):
        return {"error": "Report not found"}
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_historical_stats() -> Dict[str, Any]:
    """Aggregate stats from all reports."""
    reports = _get_reports()
    if not reports:
        return {
            "total_sessions": 0,
            "total_cost": 0,
            "total_tokens": 0,
            "total_steps": 0,
            "avg_latency_ms": 0,
            "avg_tokens_per_second": 0,
            "success_rate": 0,
            "sessions": reports,
        }

    total_cost = sum(r["summary"].get("total_cost_estimate", 0) for r in reports)
    total_tokens = sum(r["summary"].get("total_tokens", 0) for r in reports)
    total_steps = sum(r["summary"].get("total_requests", 0) for r in reports)
    total_latency = sum(r["summary"].get("total_latency_ms", 0) for r in reports)
    success_count = sum(1 for r in reports if r["status"] == "final_answer")
    tps_list = [r["summary"].get("avg_tokens_per_second", 0) for r in reports if r["summary"].get("avg_tokens_per_second", 0) > 0]

    return {
        "total_sessions": len(reports),
        "total_cost": round(total_cost, 4),
        "total_tokens": total_tokens,
        "total_steps": total_steps,
        "avg_latency_ms": round(total_latency / len(reports)) if reports else 0,
        "avg_tokens_per_second": round(sum(tps_list) / len(tps_list), 2) if tps_list else 0,
        "success_rate": round(success_count / len(reports) * 100, 1) if reports else 0,
        "sessions": reports[:50],  # Limit to 50 most recent
    }


def _get_logs(limit: int = 100) -> List[Dict[str, Any]]:
    """Read recent log entries."""
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(LOGS_DIR, f"{today}.log")
    if not os.path.exists(log_file):
        return []

    entries = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
    return entries[-limit:]


def _get_tool_usage_stats() -> Dict[str, int]:
    """Aggregate tool usage from all reports."""
    tool_usage = {}
    pattern = os.path.join(REPORTS_DIR, "session_*.json")
    for filepath in glob.glob(pattern):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            tools = data.get("summary", {}).get("tool_usage", {})
            for tool, count in tools.items():
                tool_usage[tool] = tool_usage.get(tool, 0) + count
        except Exception:
            pass
    return tool_usage


# ─────────────────────────────────────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/monitoring/historical")
async def get_historical():
    """Get aggregated historical stats and session list."""
    return _get_historical_stats()


@app.get("/api/monitoring/reports")
async def list_reports():
    """List all report files."""
    return {"reports": _get_reports()}


@app.get("/api/monitoring/reports/{filename}")
async def get_report(filename: str):
    """Get a specific report detail."""
    return _get_report_detail(filename)


@app.get("/api/monitoring/logs")
async def get_logs(limit: int = 100):
    """Get recent log entries."""
    return {"logs": _get_logs(limit)}


@app.get("/api/monitoring/tools")
async def get_tool_usage():
    """Get tool usage statistics."""
    return {"tool_usage": _get_tool_usage_stats()}


# Serve monitoring static files
os.makedirs("static/monitoring", exist_ok=True)
app.mount("/", StaticFiles(directory="static/monitoring", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("Agent Monitoring Dashboard")
    print("URL: http://127.0.0.1:8001")
    print("=" * 50)
    uvicorn.run("monitoring:app", host="127.0.0.1", port=8001, reload=True)
