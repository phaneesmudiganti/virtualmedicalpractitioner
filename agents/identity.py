import re, phonenumbers
from typing import Optional, Dict

# PAN format check (format only; not backend verification)
PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")  # Sources: GeeksforGeeks / StackOverflow refs

# Aadhaar formatting: "1234 5678 9012" and cannot start with 0/1 (format-only)
AADHAAR_REGEX = re.compile(r"^[2-9]{1}[0-9]{3}\s[0-9]{4}\s[0-9]{4}$")

def validate_pan(pan: str) -> bool:
    return bool(PAN_REGEX.match(pan.strip().upper()))

def validate_aadhaar(aadhaar: str) -> bool:
    return bool(AADHAAR_REGEX.match(aadhaar.strip()))

def validate_phone(msisdn: str, region: str="IN") -> bool:
    try:
        n = phonenumbers.parse(msisdn, region)
        return phonenumbers.is_valid_number(n)
    except Exception:
        return False

def identity_payload(name: str, age: int, id_proof_type: str, id_value: str, phone: str, email: Optional[str]=None) -> Dict:
    ok = False
    if id_proof_type.upper() == "PAN":
        ok = validate_pan(id_value)
    elif id_proof_type.upper() == "AADHAAR":
        ok = validate_aadhaar(id_value)
    else:
        ok = False
    phone_ok = validate_phone(phone)
    return {
        "verified": bool(ok and phone_ok and name and age >= 0),
        "name": name, "age": age, "id_type": id_proof_type,
        "id_value": id_value, "phone": phone, "email": email
    }