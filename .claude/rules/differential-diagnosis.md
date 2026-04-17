# Advanced Differential Diagnosis Rules (AMDA)

Apply strictly at stage 3 (preliminary diagnosis formulation) and at every probability recalculation.

## Mandatory Steps

**Step 1.** Identify the leading symptoms and their characteristics. Compare against classic disease patterns.

**Step 2.** For each potential diagnosis, explicitly state:
- Data that **supports** it (positive findings).
- Data that **excludes** it or reduces its probability (negative findings, red flags).
- Negative symptoms (what is absent but should be present).

**Step 3.** Apply the "common things are common" principle:
- First consider the most prevalent conditions for the patient's age, sex, region, and risk factors.
- Rare diagnoses only when there is strong supporting evidence or common diagnoses have been ruled out.

**Step 4.** Build the differential series:
- Top 3 most probable diagnoses.
- Less probable but must-exclude diagnoses.
- Rare / "must not miss" diagnoses (red-flag diagnoses).

**Step 5.** Calculate probabilities strictly according to **`@.claude/rules/probability-calculation.md`**:
- Prior probability — based on population prevalence + patient risk factors (age, sex, comorbidities, heredity, lifestyle habits).
- Posterior update — accounting for the likelihood ratio of symptoms and test results (positive/negative findings).
- The sum of all probabilities must always equal 100%.
- Do not use precise mathematical formulas unless necessary; rely on clinical logic.
- If data is insufficient — indicate a low confidence level and suggest priority investigations.

**Step 6.** Always separately highlight **red flags** and alarm symptoms (see `@.claude/rules/red-flags.md`).

## Diagnosis List Requirements
- No more than 7–8 diagnoses (optimally 5–6).
- For each: name (with ICD-10/ICD-11 code where possible), probability % (sum = 100%), brief rationale with inclusion/exclusion logic, confidence level (low / medium / high).

Use elimination logic. When recalculating probabilities after new data, repeat all steps following `@.claude/rules/probability-calculation.md`.

After any significant data update (new anamnesis, document analysis, probability recalculation) update patient-data/current-patient.md and create or append a record in patient-data/sessions/.
