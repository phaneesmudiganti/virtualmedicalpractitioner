from agents.identity import validate_pan, validate_aadhaar

def test_pan_ok():
    assert validate_pan("BNZAA2318J")

def test_aadhaar_ok():
    assert validate_aadhaar("3675 9834 6012")