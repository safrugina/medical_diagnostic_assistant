# AMDA Diagnostic Cycle Architecture

## Overall Project Structure
AMDA operates as a stateful agent with a clear sequential cycle:

1. Anamnesis collection (rules/anamnesis.md)
2. Document analysis (rules/document-analysis.md)
3. Differential diagnosis and preliminary diagnoses (rules/differential-diagnosis.md + probability-calculation.md)
4. Prioritized investigation plan (rules/test-prioritization.md)
5. Iterative refinement
6. Final diagnosis (at ≥ 90%) → recommendations (rules/final-diagnosis.md)

## Key Principles
- Strict sequential stage order
- Mandatory use of red flags (rules/red-flags.md)
- Qualitative Bayesian approach for probability calculation
- Maximum diagnosis elimination through highly informative tests
- Statefulness: full preservation of history, anamnesis, documents, and current probabilities

## Interaction with rules/
The main CLAUDE.md acts as the orchestrator. All detailed clinical rules are housed in `.claude/rules/`.

This file serves only as a general architectural overview.
