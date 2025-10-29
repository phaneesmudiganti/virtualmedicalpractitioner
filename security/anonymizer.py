import hashlib
from typing import Dict

def anonymize_record(pii: Dict[str, str]) -> Dict[str, str]:
    return {k: hashlib.sha256((k + ":" + str(v)).encode()).hexdigest() for k, v in pii.items()}