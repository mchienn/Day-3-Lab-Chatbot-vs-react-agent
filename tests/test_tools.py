import os
import sys

# Ensure stdout handles UTF-8 for Vietnamese characters on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add the project root directory to the python path to import src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools.medical_tools import (
    AnalyzeSymptomTool,
    CheckDoctorAvailabilityTool,
    BookAppointmentTool
)

def run_tests():
    print("==================================================")
    print("      RUNNING VERIFICATION FOR MEDICAL TOOLS      ")
    print("==================================================\n")

    # 1. Instantiate the tools
    symptom_tool = AnalyzeSymptomTool()
    availability_tool = CheckDoctorAvailabilityTool()
    booking_tool = BookAppointmentTool()

    # ==========================================
    # Test 1: AnalyzeSymptomTool
    # ==========================================
    print("--- Test 1: AnalyzeSymptomTool ---")
    test_cases_symptoms = [
        "Tôi bị đau bụng nhiều và đầy hơi khó tiêu",
        "Bị ho khan, sổ mũi và hơi khó thở",
        "Thường xuyên đau đầu mất ngủ chóng mặt",
        "Có nốt ngứa nổi mẩn dị ứng ngoài da",
        "Triệu chứng bất kỳ không có trong danh mục"
    ]
    for symptoms in test_cases_symptoms:
        # Test execute() directly
        res_direct = symptom_tool.execute(symptoms)
        # Test execute_from_string()
        res_str = symptom_tool.execute_from_string(f'"{symptoms}"')
        print(f"Symptoms: '{symptoms}'")
        print(f"  -> Specialty (Direct): {res_direct}")
        print(f"  -> Specialty (String Args): {res_str}\n")


    # ==========================================
    # Test 2: CheckDoctorAvailabilityTool
    # ==========================================
    print("--- Test 2: CheckDoctorAvailabilityTool ---")
    test_cases_availability = [
        {"specialty": "Khoa Tiêu hóa", "date": "2026-06-02"},
        {"specialty": "Khoa Hô hấp", "date": "2026-06-02"},
        {"specialty": "Khoa Tiêu hóa", "date": "2026-06-04"},  # No doctor available for this date
        {"specialty": "Khoa Thần kinh", "date": "2026-06-03"},
        {"specialty": "Khoa Không Tồn Tại", "date": "2026-06-02"}  # Specialty not found
    ]
    for case in test_cases_availability:
        specialty = case["specialty"]
        date = case["date"]
        # Test execute() directly
        res_direct = availability_tool.execute(specialty=specialty, date=date)
        # Test execute_from_string()
        arg_str = f'"{specialty}", "{date}"'
        res_str = availability_tool.execute_from_string(arg_str)
        print(f"Params: Specialty='{specialty}', Date='{date}'")
        print(f"  -> Result (Direct):\n{res_direct}")
        print(f"  -> Result (String Args):\n{res_str}\n")


    # ==========================================
    # Test 3: BookAppointmentTool
    # ==========================================
    print("--- Test 3: BookAppointmentTool ---")
    # Test execute() directly
    res_direct = booking_tool.execute(
        patient_name="Nguyễn Văn A",
        doctor_name="BS. Trần Văn A",
        datetime="2026-06-02 08:00"
    )
    # Test execute_from_string()
    arg_str = '"Nguyễn Văn A", "BS. Trần Văn A", "2026-06-02 08:00"'
    res_str = booking_tool.execute_from_string(arg_str)
    
    print("Params: Patient='Nguyễn Văn A', Doctor='BS. Trần Văn A', Time='2026-06-02 08:00'")
    print(f"  -> Result (Direct): {res_direct}")
    print(f"  -> Result (String Args): {res_str}\n")

    print("==================================================")
    print("      ALL TOOL TESTS COMPLETED SUCCESSFULLY       ")
    print("==================================================")

if __name__ == "__main__":
    run_tests()
