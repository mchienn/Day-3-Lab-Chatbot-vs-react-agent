import re

def check_red_flags(symptoms: str) -> str:
    """
    Analyzes symptoms to detect emergency conditions (red flags).
    
    Args:
        symptoms (str): Patient described symptoms.
        
    Returns:
        str: Diagnostic evaluation of any red flags found.
    """
    symptoms_lower = symptoms.lower()
    
    # Emergency definitions
    emergencies = {
        "Chest pain with shortness of breath": ["chest pain", "tightness in chest", "gasping", "shortness of breath", "hard to breathe"],
        "Stroke symptoms": ["stroke", "facial drooping", "droop", "arm weakness", "slurred speech", "numbness on one side", "cant speak"],
        "Severe bleeding": ["severe bleeding", "gushing blood", "uncontrolled bleeding", "heavy bleeding"],
        "Loss of consciousness": ["loss of consciousness", "passed out", "fainted", "unconscious", "blacked out"],
        "Seizures": ["seizure", "seizures", "convulsion", "fits", "spasm"]
    }
    
    detected = []
    for emergency, keywords in emergencies.items():
        for keyword in keywords:
            if keyword in symptoms_lower:
                detected.append(emergency)
                break
                
    if detected:
        return f"EMERGENCY DETECTED: Red flags found: {', '.join(detected)}. Urgent medical intervention is required. Patient must be routed to emergency services immediately."
    
    return "No emergency red flags detected. Proceed with standard specialty recommendation."

def recommend_specialty(symptoms: str) -> str:
    """
    Recommends a medical specialty based on patient described symptoms.
    
    Args:
        symptoms (str): Patient described symptoms.
        
    Returns:
        str: The recommended department.
    """
    symptoms_lower = symptoms.lower()
    
    specialties = {
        "Cardiology": ["heart", "cardio", "chest pain", "palpitation", "arrhythmia", "murmur", "high blood pressure"],
        "Neurology": ["brain", "neurolog", "headache", "migraine", "dizzy", "numbness", "seizure", "stroke", "tremor", "paralysis"],
        "Gastroenterology": ["stomach", "gastric", "belly", "diarrhea", "vomit", "nausea", "bloated", "cramp", "constipation", "digestion", "acid reflux"],
        "Pediatrics": ["child", "baby", "pediatric", "kid", "infant", "toddler"],
        "Orthopedics": ["bone", "joint", "fracture", "knee", "wrist", "shoulder", "ankle", "sprain", "muscle pain", "arthritis", "back pain"],
        "Pulmonology": ["lung", "breath", "asthma", "cough", "wheezing", "pneumonia", "bronchitis"],
        "Dermatology": ["skin", "rash", "itch", "acne", "eczema", "hives", "dermatitis"],
        "ENT": ["ear", "nose", "throat", "sinus", "tonsil", "hearing", "throat pain", "otitis"]
    }
    
    for specialty, keywords in specialties.items():
        for keyword in keywords:
            if keyword in symptoms_lower:
                return f"RECOMMENDED SPECIALTY: {specialty}. Confirmed based on symptoms related to: '{keyword}'."
                
    return "RECOMMENDED SPECIALTY: General Medicine. Reason: Symptoms do not clearly align with a specific department, starting with general consultation."

def transfer_booking(specialty: str) -> str:
    """
    Initiates booking routing for the recommended specialty.
    
    Args:
        specialty (str): The name of the medical specialty department.
        
    Returns:
        str: Status statement of the booking routing.
    """
    # Clean the input specialty name (strip prefixes if any)
    clean_specialty = specialty.replace("RECOMMENDED SPECIALTY:", "").replace("department", "").strip(" .\"'")
    
    return f"BOOKING_SUCCESS: Booking workflow initiated for the '{clean_specialty}' department. Patient profile has been transferred to BookingAgent."
