import requests
import json

def test_flow():
    base_url = "http://127.0.0.1:8000"
    
    # 1. Create a session
    print("Creating session...")
    resp = requests.post(f"{base_url}/api/sessions", json={"title": "Test Flow Session"}, timeout=10)
    assert resp.status_code == 201, f"Failed to create session: {resp.text}"
    session_id = resp.json()["id"]
    print(f"Session created: {session_id}\n")

    # Helper function to send message
    def send_msg(msg):
        print(f"Patient: {msg}")
        payload = {
            "message": msg,
            "session_id": session_id
        }
        resp = requests.post(f"{base_url}/api/chat", json=payload, timeout=20)
        assert resp.status_code == 200, f"Chat failed: {resp.text}"
        data = resp.json()
        print(f"Agent: {data['reply']}")
        print(f"Metrics: Latency: {data.get('latency_ms')}ms, Steps: {data.get('steps')}\n")
        return data['reply']

    # Step 1: Send symptoms
    send_msg("Tôi bị đau bụng, đầy hơi, khó tiêu")

    # Step 2: Send tomorrow
    send_msg("ngày mai")

    # Step 3: Send availability check
    send_msg("có những ngày nào trống và có lịch")

if __name__ == "__main__":
    test_flow()
