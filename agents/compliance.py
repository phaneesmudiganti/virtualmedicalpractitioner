from datetime import datetime
from core.constants import CONSENT_PURPOSES

DPDP_NOTICE = (
    "We request your explicit consent to collect and process your personal and health data "
    "for the listed purposes. You may withdraw consent anytime; withdrawal is as easy as giving it. "
    "Data will be retained only as necessary and protected with encryption and access controls. "
    "Your rights: access, correction, erasure, grievance redressal. "
    "Processing follows India’s DPDP Act, 2023 and applicable IT Act/SPDI Rules until fully superseded. "
)

def generate_consent(language: str = "en", include_storage_period: str = "Minimum 3 years (indoor patient records)"):
    # Sources: DPDP Consent principles; retention from legacy MCI/NMC ethics guidance
    # DPDP: MeitY Gazette; PwC summary. Retention: IMA/MCI; CAHO.
    return {
        "notice": DPDP_NOTICE,
        "purposes": CONSENT_PURPOSES,
        "storage_period": include_storage_period,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "language": language
    }
