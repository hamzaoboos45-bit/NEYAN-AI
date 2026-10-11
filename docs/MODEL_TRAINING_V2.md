# NEYAN NLP training V2 runbook

## Data and split policy

Run `python training_data/build_dataset_v2.py` first. It creates:

- `training_data/chat_intents_v2.jsonl` — 1,200 train and 300 validation rows.
- `training_data/chat_intents_challenge_test.jsonl` — 150 external challenge rows.

The training command must receive only the V2 train/validation file. Do not
pass the challenge file, legacy test rows, or any production chat history into
training or hyperparameter selection.

## Required experiment protocol

Use a fixed seed and record Python, torch, transformers, device, dataset hash,
model ID, frozen layers, max length, batch size, learning rate, dropout,
weight decay, early-stopping epoch, and validation metrics. Compare head-only,
stronger head, final 1–2 layers, and final 3–4 layers using validation only.
Run the winning validation configuration across seeds `20260920`, `20260921`,
and `20260922`; report mean and standard deviation.

Only after choosing the configuration may an operator run the independent
legacy and Challenge evaluations once. Promotion requires improvement over the
legacy artifact on both external tests, no critical intent F1 below 0.70, and
full application regression success. Save the result as
`arabert_intent_delta_v2.pt` with `chat_intent_metadata_v2.json`; do not
overwrite `arabert_intent_delta.pt` until those gates pass.

## Evaluation

`python scripts/evaluate_chat_model_v2.py` performs the data-isolation check,
records a rule-only reference, and writes `docs/CHAT_MODEL_EVALUATION_V2.json`.
When a valid V2 artifact and optional ML dependencies are available, the
script can be extended/run in that environment to emit model-only and hybrid
results. Its evaluation code never changes the training corpus.

## Current status

V2 data integrity has been generated and checked. Training and model metrics
are intentionally pending a dependency-enabled environment; no V2 artifact is
promoted in this checkout.
