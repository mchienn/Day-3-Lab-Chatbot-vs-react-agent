import os
import json
import random
from typing import Dict, Any
from src.tools.base import BaseTool

# Dynamically resolve file paths relative to this file's directory
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SYMPTOMS_PATH = os.path.abspath(os.path.join(CURRENT_DIR, "..", "data", "symptoms_mapping.json"))
DOCTORS_PATH = os.path.abspath(os.path.join(CURRENT_DIR, "..", "data", "doctors_schedule.json"))

class AnalyzeSymptomTool(BaseTool):
    """
    Tool to analyze a patient's symptoms and match them to the most suitable medical specialty.
    """
    def __init__(self):
        super().__init__(
            name="AnalyzeSymptomTool",
            description=(
                "Use this tool to analyze a patient's symptoms and determine the most appropriate medical specialty. "
                "Input must be a string containing symptoms (e.g., 'đau bụng, buồn nôn')."
            )
        )

    def execute(self, symptoms_text: str) -> str:
        """
        Processes symptoms and returns the recommended medical specialty.

        Args:
            symptoms_text: Plain text describing the patient's symptoms.

        Returns:
            str: Name of the specialty (e.g., 'Khoa Tiêu hóa') or a default clinic department.
        """
        if not symptoms_text or not isinstance(symptoms_text, str):
            return "Error: Input symptoms_text must be a non-empty string."

        try:
            if not os.path.exists(SYMPTOMS_PATH):
                return "Error: Symptoms mapping file not found."

            with open(SYMPTOMS_PATH, "r", encoding="utf-8") as f:
                mapping = json.load(f)

            symptoms_lower = symptoms_text.lower()
            
            # Loop through mapped specialties and check if any keyword matches
            for key, data in mapping.items():
                keywords = data.get("keywords", [])
                for keyword in keywords:
                    if keyword.lower() in symptoms_lower:
                        return data.get("specialty_name", "Khoa Khám Bệnh Đa Khoa")

            # Fallback if no keywords matched
            return "Khoa Khám Bệnh Đa Khoa"

        except json.JSONDecodeError:
            return "Error: Failed to parse symptoms mapping data. The JSON file is corrupt."
        except Exception as e:
            return f"Error: An unexpected error occurred while analyzing symptoms. Details: {str(e)}"


class CheckDoctorAvailabilityTool(BaseTool):
    """
    Tool to check the available time slots for doctors in a specific specialty on a given date.
    """
    def __init__(self):
        super().__init__(
            name="CheckDoctorAvailabilityTool",
            description=(
                "Use this tool to check the available time slots for doctors based on a specific specialty and date. "
                "Input parameters: specialty (string, e.g., 'Khoa Tiêu hóa'), date (string, format YYYY-MM-DD, e.g., '2026-06-02')."
            )
        )

    def execute(self, specialty: str, date: str) -> str:
        """
        Filters doctor schedules by specialty and date, returning the availability.

        Args:
            specialty: The name of the medical specialty (e.g., 'Khoa Hô hấp').
            date: The date to check in YYYY-MM-DD format (e.g., '2026-06-02').

        Returns:
            str: JSON string containing a list of available doctors and slots,
                 or an error/explanation message.
        """
        if not specialty or not date:
            return "Error: Both 'specialty' and 'date' arguments are required."

        specialty = specialty.strip()
        date = date.strip()

        try:
            if not os.path.exists(DOCTORS_PATH):
                return "Error: Doctors schedule file not found."

            with open(DOCTORS_PATH, "r", encoding="utf-8") as f:
                doctors = json.load(f)

            available_doctors = []
            specialty_found = False

            for doc in doctors:
                doc_specialty = doc.get("specialty", "")
                if doc_specialty.lower() == specialty.lower():
                    specialty_found = True
                    schedule = doc.get("schedule", {})
                    if date in schedule:
                        slots = schedule[date]
                        morning = slots.get("morning", [])
                        afternoon = slots.get("afternoon", [])
                        # Only include doctors who have at least one slot available
                        if morning or afternoon:
                            available_doctors.append({
                                "doctor_name": doc.get("doctor_name"),
                                "specialty": doc_specialty,
                                "available_slots": {
                                    "morning": morning,
                                    "afternoon": afternoon
                                }
                            })

            if not specialty_found:
                return f"No doctors found for specialty '{specialty}'. Please double-check the specialty name."

            if not available_doctors:
                return f"No available doctors found for specialty '{specialty}' on date {date}. Please try another date."

            return json.dumps(available_doctors, ensure_ascii=False, indent=2)

        except json.JSONDecodeError:
            return "Error: Failed to parse doctors schedule data. The JSON file is corrupt."
        except Exception as e:
            return f"Error: An unexpected error occurred while checking availability. Details: {str(e)}"


class BookAppointmentTool(BaseTool):
    """
    Tool to book an appointment with a chosen doctor at a specific date/time.
    """
    def __init__(self):
        super().__init__(
            name="BookAppointmentTool",
            description=(
                "Use this tool strictly to finalize the booking after confirming the doctor, date, and time with the patient. "
                "Input parameters: patient_name (string), doctor_name (string), datetime (string, format YYYY-MM-DD HH:MM, e.g., '2026-06-02 08:00')."
            )
        )

    def execute(self, patient_name: str, doctor_name: str, datetime: str) -> str:
        """
        Executes the booking and returns confirmation with a reference code.

        Args:
            patient_name: Name of the patient.
            doctor_name: Name of the doctor.
            datetime: The date and time of the appointment (e.g., '2026-06-02 08:00').

        Returns:
            str: A plain text booking confirmation message.
        """
        if not patient_name or not doctor_name or not datetime:
            return "Error: 'patient_name', 'doctor_name', and 'datetime' are all required parameters."

        try:
            # Generate a booking reference code: TK- followed by 4 random digits
            ref_num = random.randint(1000, 9999)
            booking_reference = f"TK-{ref_num}"

            # Format the output message
            confirmation = (
                f"Đặt lịch thành công! Mã cuộc hẹn: {booking_reference}. "
                f"Bệnh nhân: {patient_name.strip()}, "
                f"Bác sĩ: {doctor_name.strip()}, "
                f"Thời gian: {datetime.strip()}."
            )
            return confirmation

        except Exception as e:
            return f"Error: An unexpected error occurred during the booking process. Details: {str(e)}"
