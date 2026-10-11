# NEYAN NLP V2 Evaluation

## Artifact
- Directory: `backend/nlp/models/v2_exp_partial2_seed20260920`
- Base model: `aubmindlab/bert-base-arabertv02`
- Best validation epoch: `13`
- Device: `cuda`
- Confidence threshold: `0.6`

## Untouched Challenge Test
- Samples: 150
- Model-only Accuracy: **38.67%**
- Model-only Macro F1: **37.48%**
- Model-only Weighted F1: **37.48%**
- Hybrid Accuracy: **43.33%**
- Hybrid Macro F1: **46.96%**
- Hybrid Weighted F1: **46.96%**

## Legacy Test
- Samples: 45
- Model-only Accuracy: **40.00%**
- Model-only Macro F1: **37.64%**
- Hybrid Accuracy: **68.89%**
- Hybrid Macro F1: **69.71%**

## Latency
- Mean: 9.52 ms
- Median: 8.56 ms
- P95: 16.45 ms

## Integrity
The challenge corpus was loaded only by this evaluation script after the
trained artifact already existed. Training/model selection must remain based
only on the train + validation corpus.
