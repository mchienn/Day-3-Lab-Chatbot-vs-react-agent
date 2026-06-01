import requests
import json

url = "http://127.0.0.1:8000/api/chat"
# Use the session ID created in the previous test
session_id = "14fc63d3-800a-48fb-be21-2c45c087d1d4"

payload = {
    "message": "ngày mai",
    "session_id": session_id
}
headers = {
    "Content-Type": "application/json"
}

try:
    print(f"Sending follow-up request for session {session_id}...")
    response = requests.post(url, json=payload, headers=headers, timeout=15)
    print(f"Status Code: {response.status_code}")
    print("Response JSON:")
    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
except Exception as e:
    print(f"Error: {e}")
