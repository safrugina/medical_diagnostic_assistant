# Data Import Rules from EMIAS and Clinic Personal Accounts (AMDA)

## Supported Sources
- EMIAS (Moscow) — personal account / EMIAS.INFO app
- Personal accounts of private clinics and laboratories (Invitro, Helix, Gemotest, SberZdorovye, DocDoc, "Medsi", "SM-Clinic", "K+31" clinics, etc.)

## Automatic Import (Recommended Method)
The user runs the script from the `./scripts/` folder, which:
1. Authenticates with the source (credentials are requested interactively or via .env).
2. Downloads data from the last 180 days.
3. Saves files to the appropriate subfolders of documents/.

After the script runs, the agent automatically:
- Scans for new files in documents/appointments, documents/medical_tests, documents/medical_researches
- Performs OCR + analysis (see document-analysis.md)
- Updates patient-data/current-patient.md

## Manual Import (Fallback)
The user independently downloads documents from the personal account and places them in the appropriate subfolders. The agent recognizes them automatically.

## Mandatory Agent Actions
When the user commands "Import data from EMIAS for the last 6 months" or "Run import":
- Check for scripts in ./scripts/
- Suggest running the appropriate script
- After import completion — immediately run full analysis of new documents
- Update current-patient.md and diagnostic-log.md

→ Detailed integration rules: @.claude/rules/emr-integration.md
