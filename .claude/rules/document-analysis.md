# Medical Document Analysis Rules (AMDA)

## Mandatory Analysis Order
When new files are received in the `./documents/` folder (PDF, JPG, PNG, DOCX, etc.):

1. State the file name, document type, and date (if available).
2. **Automatically activate multimodal analysis and OCR** in Claude:
   - For PDFs: use both text extraction and visual analysis of each page.
   - For images (JPG, PNG, scanned forms): perform **full text recognition (OCR)**.
     - For FHIR Bundle (JSON) and SEMD, perform structured parsing of Ru Core resources.

3. Identify **all key indicators** with reference values (use docs/common-lab-reference.md).
4. Mark deviations (↑ / ↓ / within normal range) and their clinical significance.
5. Save data in structured form (Markdown tables).

## Special Text Recognition (OCR) Rules

**Always perform the following steps during analysis:**

### FHIR and SEMD
- When receiving FHIR Bundle or individual resources (Patient, Observation, DiagnosticReport, etc.) — perform mapping according to **Ru Core**.
- Specify: "Data received via FHIR Ru Core / export from [MIS name]".
- Main resources to parse: Patient, Observation, DiagnosticReport, Condition, Bundle.
- When discrepancies with Ru Core ValueSet are found — explicitly note this.

- **If the document is an image or a scanned PDF** (poor text extraction):
  - Perform detailed OCR recognition of all visible text.
  - Accurately transcribe tables: columns "Parameter", "Result", "Reference", "Units".
  - Preserve data layout (e.g., "Hemoglobin 142 g/L (130–170)").
  - If handwritten text or laboratory stamps are present — note this explicitly.

- **If recognition quality is low** (blurry, low resolution, heavy tilt):
  - Report: "Image quality is low; OCR errors are possible. It is recommended to retake the photo with better lighting and a resolution of ≥ 1000 × 1000 px."
  - Still provide the most complete transcription possible.

- **For multi-page documents**:
  - State "Page X of Y".
  - Consolidate data from all pages into a single structured table.

## Translation Rule (Mandatory)
After extracting all text and indicators from a document, **translate all parameter names, units, and clinical terms into English** before saving or displaying results. This applies regardless of the original document language (Russian, German, etc.).

- **Table column headers** → English (e.g., "Показатель" → "Parameter", "Результат" → "Result", "Референс" → "Reference Values", "Единицы" → "Units")
- Parameter names → English standard clinical terminology (e.g., "Гемоглобин" → "Hemoglobin", "Лейкоциты" → "WBC (Leukocytes)")
- Units → international standard (e.g., "г/л" → "g/L", "мкмоль/л" → "µmol/L")
- Deviation markers and clinical significance descriptions → English
- Document type and section headings → English
- Original values and numbers are preserved as-is; only labels are translated

If a term has no direct English equivalent, provide the original in parentheses after the translation.

## Output Format
Always use the following table:
| Parameter | Result | Reference Values | Deviation | Clinical Significance |

After any significant data update (new anamnesis, document analysis, probability recalculation) update patient-data/current-patient.md and create or append a record in patient-data/sessions/.

**It is prohibited** to proceed to diagnosis formulation until all uploaded documents have been fully analyzed.
