import unittest
from unittest.mock import MagicMock, patch
import json
import os
import sys

# Add project root to sys.path to import chatbot
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chatbot import triage_patient

class TestChatbotTriage(unittest.TestCase):
    def setUp(self):
        # Set a dummy API key if not already set to prevent initialization check failure
        self.patcher = patch.dict(os.environ, {"OPENAI_API_KEY": "dummy-api-key-for-testing"})
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()

    @patch("chatbot.OpenAI")
    def test_successful_triage_emergency(self, mock_openai_class):
        # Setup mocks
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_message = MagicMock()
        mock_message.content = json.dumps({
            "urgency": "Emergency",
            "specialty": "Cardiology",
            "confidence": 0.98,
            "next_step": "BookingAgent"
        })
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        
        mock_response.usage.prompt_tokens = 150
        mock_response.usage.completion_tokens = 45
        mock_response.usage.total_tokens = 195
        
        mock_client.chat.completions.create.return_value = mock_response

        # Execute
        result = triage_patient("I am experiencing severe chest pain and short of breath.")

        # Assertions
        self.assertEqual(result["urgency"], "Emergency")
        self.assertEqual(result["specialty"], "Cardiology")
        self.assertEqual(result["confidence"], 0.98)
        self.assertEqual(result["next_step"], "BookingAgent")
        self.assertEqual(result["_meta"]["total_tokens"], 195)
        self.assertEqual(result["_meta"]["prompt_tokens"], 150)
        self.assertEqual(result["_meta"]["completion_tokens"], 45)

    @patch("chatbot.OpenAI")
    def test_triage_vague_input(self, mock_openai_class):
        # Setup mocks
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_message = MagicMock()
        mock_message.content = json.dumps({
            "urgency": "Low",
            "specialty": "None",
            "confidence": 0.0,
            "next_step": "Clarify"
        })
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 30
        mock_response.usage.total_tokens = 130
        
        mock_client.chat.completions.create.return_value = mock_response

        # Execute
        result = triage_patient("Hello, I need some help.")

        # Assertions
        self.assertEqual(result["urgency"], "Low")
        self.assertEqual(result["specialty"], "None")
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["next_step"], "Clarify")

    @patch("chatbot.OpenAI")
    def test_json_parsing_fallback(self, mock_openai_class):
        # Setup mocks to return invalid JSON
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        mock_response = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "This is not a JSON object"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        
        mock_client.chat.completions.create.return_value = mock_response

        # Execute
        result = triage_patient("My head hurts")

        # Assertions (should fallback gracefully to predefined error-handling schema)
        self.assertEqual(result["next_step"], "Clarify")
        self.assertEqual(result["confidence"], 0.0)
        self.assertIn("error", result)

if __name__ == "__main__":
    unittest.main()
