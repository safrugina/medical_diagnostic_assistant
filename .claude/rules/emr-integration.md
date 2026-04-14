# AMDA Integration Rules with EMR/EHR and Russian Medical Information Systems

**Version:** 1.1 (April 2026)

## General Integration Policy
AMDA is a local assistive diagnostic agent.  
All operations with personal medical data (PHI) must be performed **in compliance with Federal Law 152-FZ**, EGISZ requirements, and the data minimization principle.

**Acceptable Integration Levels (by security and feasibility priority):**

1. **Manual / File Exchange** (primary and recommended for the current AMDA version)
2. **FHIR API via middleware** (recommended for production)
3. **Deep embedded integration** (only after certification as a medical device)

## Current FHIR Status in Russia (2026)

- The main national profile is **FHIR Ru Core** (developed by the HL7 FHIR Russia community together with the Central Research Institute of Public Health Organization and Medical Information Technologies, St. Petersburg MIAC, Netrika, 1C, and others).
- FHIR is actively used as **de-facto standard** for new EGISZ modules (oncological consultation, patient flow management, personal medical assistants).
- In 2025–2026, the inclusion of FHIR in the EGISZ contract is being discussed.
- Work continues on GOSTs for profiling and implementation guides.
- SEMD (structured electronic medical documents) based on HL7 CDA remain the primary format for REMD, but are increasingly supplemented or duplicated by FHIR resources (especially laboratory research protocols — LIS).

**Key Resources:**
- Community website: https://fhir.ru/
- Ru Core Implementation Guide: https://fhir-ru.github.io/core/ and GitHub fhir-ru/core
- Main resources in use: Patient, Observation, DiagnosticReport, Condition, Encounter, Bundle

## Supported Formats and Mechanisms

### 1. File Exchange (Level 1)
- PDF, JPG/PNG (with OCR)
- FHIR Bundle (JSON)
- SEMD / REMD (XML based on CDA)
- MIS exports (1C:Medicine, Netrika, Barkli, etc.)

**Mandatory AMDA Actions:**
- When receiving FHIR Bundle or JSON — perform structured parsing of Ru Core resources.
- Map data to `patient-data/current-patient.md` (demographics → Patient, laboratory values → Observation, conclusions → DiagnosticReport).
- When generating recommendations, produce easily importable text (or simple FHIR Bundle for Condition/DiagnosticReport).

### 2. FHIR API Integration (Level 2)
The recommended approach for production use is **middleware/proxy**:
- OAuth2 / SMART on FHIR authorization
- Requests to Patient, Observation, DiagnosticReport, and other resources
- De-identification or minimally necessary data before transmission to AMDA
- Return of recommendations as Draft DiagnosticReport or ClinicalImpression

**Important:** Direct AMDA integration with EMR without middleware is **not recommended** due to security and compliance requirements.

## Mandatory Rules for AMDA

- Always explicitly specify the data source: "Data received from [MIS name] via FHIR Ru Core / SEMD export".
- When parsing laboratory data, use mappings of the Ministry of Health NSI reference books (Ru Core ValueSet).
- When working with identifiers, account for Russian systems: SNILS, OMS policy, medical record number, identity documents (NSI EGISZ).
- When critical data (red flags) is detected — highlight them immediately regardless of source.
- Never request direct EMR access without explicit user confirmation and compliance with all information security requirements.

## Limitations and Prohibitions

- It is prohibited to store or transmit PHI data outside the local project without user consent and use of approved connectors.
- It is prohibited to automatically write data back to EMR without physician involvement.
- When in doubt about format compatibility, state: "It is recommended to verify the Ru Core profile compliance and the requirements of the specific MIS / EGISZ for 2026."

## Recommendations for Development
- Monitor Ru Core updates and HL7 FHIR Russia community discussions (weekly meetings).
- When scaling the project, consider using certified FHIR gateways and platforms (N3.Health, Netrika, etc.).
- For a full-fledged CDSS (Clinical Decision Support System), integration must undergo certification as a medical device.

## Automated Import from EMIAS and Clinic Personal Accounts (2026)

Supported via browser automation (Playwright/Selenium).  
Direct FHIR API for patients in EMIAS is not available (only system-level Ru Core).

Scripts are located in `./scripts/`.  
Credentials are **never** saved in the project — they are entered on each run or via secure .env.

The agent can run scripts on user command.

**Information currency date:** April 2026.  
If there are significant changes in regulations or Ru Core — update this file.
