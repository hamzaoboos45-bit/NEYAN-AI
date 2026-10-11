# NEYAN NLP V3 experiment plan

## Data freeze

- `chat_intents_v3.jsonl`: 3,000 train / 450 validation rows, 15 labels.
- `chat_intents_final_holdout_v3.jsonl`: 300 rows, 20 per label.
- The retired V2 Challenge is development diagnostic only; see
  `CHAT_CHALLENGE_AUDIT_V3.md`.
- Training code must only read the V3 train/validation file. The V3 final
  holdout is excluded from imports and command-line defaults.

## Validation-only selection

From a local dependency-enabled environment, compare head-only and final
1/2/3-layer configurations over seeds 20260920, 20260921, and 20260922.
Choose from validation Macro F1 mean, standard deviation, and per-intent
performance only. Do not run a final-holdout score at this stage.

```powershell
python scripts\train_chat_model_v3.py --validate-only
python scripts\train_chat_model_v3.py --seed 20260920 --unfreeze-last-layers 0 --output-dir artifacts\v3-head
python scripts\train_chat_model_v3.py --seed 20260920 --unfreeze-last-layers 1 --encoder-learning-rate 0.00002 --output-dir artifacts\v3-layer1
python scripts\train_chat_model_v3.py --seed 20260920 --unfreeze-last-layers 2 --encoder-learning-rate 0.00002 --output-dir artifacts\v3-layer2
python scripts\train_chat_model_v3.py --seed 20260920 --unfreeze-last-layers 3 --encoder-learning-rate 0.00002 --output-dir artifacts\v3-layer3
```

After all architecture/rule/threshold choices are frozen, a separate V3
evaluator must open the final holdout once and write immutable evidence. V3 is
not a runtime candidate until that evaluation and the full application
regression pass. V1 stays active; V2 remains historical evidence only.
