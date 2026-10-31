# NEYAN NLP V2 evaluation record

This file records reproducible dataset evidence, not an invented model result.

## Dataset integrity

- V2 corpus: 1,500 rows, 15 existing intent labels.
- Split: 1,200 train and 300 validation; every label has 80/20 rows.
- External Challenge Test: 150 rows, 10 per label.
- V2 SHA-256: `8e29105e7054a3e90403141a948f3ce63c81ca59d7feea9c0f25c97875080acd`
- Challenge SHA-256: `5bd53c25fbfea99f7e6d26dee5adb2a025d077bce38639327d0afef9373563d0`
- Legacy held-out SHA-256: `82dd238c0fd950f0b4fa1417dd3266875ed9359f88bf6b3cd526b6dd425278f6`
- Exact normalized duplicate, family leakage, PII, and cross-corpus near-duplicate checks: pass.

## Measured result available in this environment

The deterministic rule-only reference on the external Challenge Test is
Accuracy **13.33%** and Macro F1 **17.14%**. It is a diagnostic baseline for
the new harder corpus, not a model-selection signal and not a final hybrid
claim. Full structured confusion data and examples are in
`CHAT_MODEL_EVALUATION_V2.json`.

## Model and hybrid status

`torch`, `transformers`, and the AraBERT base weights are unavailable in this
execution environment. Therefore no V2 trained-model, semantic, or hybrid
metric was produced, no latency benchmark was produced, and no V2 artifact was
created or promoted. The checked-in V1 delta remains untouched.

Run the V2 training protocol only in a dependency-enabled isolated environment
and then evaluate the untouched legacy and Challenge sets after configuration
selection. Never use this Challenge result for hyperparameter tuning.
