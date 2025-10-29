# Medication Sources (India)

- **Regulatory approvals**: Use CDSCO/DCGI official notifications and databases (SUGAM).  
  CDSCO Home: https://cdsco.gov.in/opencms/opencms/en/Home  
  Functions: https://www.cdsco.gov.in/opencms/opencms/en/About-us/Functions/

- **Rx vs Non-prescription**: India relies on **Schedules H/H1/X** for prescription-only controls; items *not* in these schedules typically function as OTC/non-prescription.  
  OPPI FAQs: https://www.indiaoppi.com/wp-content/uploads/2024/08/OPPI_FAQs-Over_the_Counter_Drugs.pdf  
  Schedule H: https://en.wikipedia.org/wiki/Schedule_H  
  Medindia explainer (Schedule H/H1): https://www.medindia.net/health/drugs/drugs-and-cosmetics-rules-schedule-h-schedule-h1-drugs.htm

- **Production adapter**: Implement a `cdsco_adapter.py` that:
  1) looks up molecules/brands,
  2) maps to schedules,
  3) caches results,
  4) exposes `search(query) -> MedRecord[]`.