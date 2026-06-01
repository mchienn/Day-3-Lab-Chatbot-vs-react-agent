import os
import sys
import json
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools.medical_tools import (
    AnalyzeSymptomTool,
    CheckDoctorAvailabilityTool,
    BookAppointmentTool,
)


# Load test data from src/data/
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src", "data")

with open(os.path.join(DATA_DIR, "symptoms_mapping.json"), "r", encoding="utf-8") as f:
    SYMPTOMS_MAP = json.load(f)

with open(os.path.join(DATA_DIR, "doctors_schedule.json"), "r", encoding="utf-8") as f:
    DOCTORS_SCHEDULE = json.load(f)


# --- Test Cases from symptoms_mapping.json ---
# Build test cases dynamically from data file
SYMPTOM_TEST_CASES = []
for key, data in SYMPTOMS_MAP.items():
    specialty = data["specialty_name"]
    # Use first keyword as test input
    keyword = data["keywords"][0]
    SYMPTOM_TEST_CASES.append((keyword, specialty))


class TestAnalyzeSymptomTool:
    """Test symptom analysis tool against symptoms_mapping.json data."""

    def setup_method(self):
        self.tool = AnalyzeSymptomTool()

    @pytest.mark.parametrize("keyword,expected_specialty", SYMPTOM_TEST_CASES)
    def test_symptom_keyword_matches_specialty(self, keyword, expected_specialty):
        """Test that each keyword in symptoms_mapping maps to correct specialty."""
        result = self.tool.execute(symptoms_text=keyword)
        assert expected_specialty in result, \
            f"Keyword '{keyword}' should map to '{expected_specialty}', got: {result}"

    def test_empty_input_returns_error(self):
        result = self.tool.execute(symptoms_text="")
        assert "Error" in result

    def test_unknown_symptom_returns_general(self):
        result = self.tool.execute(symptoms_text="cảm thấy rất lạ")
        assert "Đa Khoa" in result


class TestCheckDoctorAvailabilityTool:
    """Test doctor availability tool against doctors_schedule.json data."""

    def setup_method(self):
        self.tool = CheckDoctorAvailabilityTool()

    def test_tieu_hoa_available(self):
        """Test Khoa Tiêu hóa availability on 2026-06-02."""
        result = self.tool.execute(specialty="Khoa Tiêu hóa", date="2026-06-02")
        assert "Trần Văn A" in result or "08:00" in result

    def test_ho_hap_available(self):
        """Test Khoa Hô hấp availability on 2026-06-02."""
        result = self.tool.execute(specialty="Khoa Hô hấp", date="2026-06-02")
        assert "Lê Thị B" in result or "07:30" in result

    def test_than_kinh_available(self):
        """Test Khoa Thần kinh availability on 2026-06-02."""
        result = self.tool.execute(specialty="Khoa Thần kinh", date="2026-06-02")
        assert "Phạm Quang C" in result or "14:30" in result

    def test_no_doctor_on_invalid_date(self):
        """Test that invalid date returns no availability."""
        result = self.tool.execute(specialty="Khoa Tiêu hóa", date="2099-01-01")
        assert "No available" in result or "not found" in result

    def test_unknown_specialty(self):
        result = self.tool.execute(specialty="Khoa Tim mạch", date="2026-06-02")
        assert "No doctors found" in result


class TestBookAppointmentTool:
    """Test appointment booking tool."""

    def setup_method(self):
        self.tool = BookAppointmentTool()

    def test_booking_success(self):
        result = self.tool.execute(
            patient_name="Nguyễn Văn A",
            doctor_name="BS. Trần Văn A",
            datetime="2026-06-02 08:00"
        )
        assert "TK-" in result
        assert "Nguyễn Văn A" in result
        assert "Trần Văn A" in result

    def test_booking_missing_params(self):
        result = self.tool.execute(patient_name="", doctor_name="", datetime="")
        assert "Error" in result


class TestToolDictFormat:
    """Test that tools convert correctly to agent dict format."""

    def test_to_agent_dict(self):
        tool = AnalyzeSymptomTool()
        d = tool.to_agent_dict()
        assert "name" in d
        assert "description" in d
        assert "function" in d
        assert callable(d["function"])
