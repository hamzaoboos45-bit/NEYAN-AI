# NEYAN Arabic intent classification — V2 error analysis

## Evidence source and decision flow

The recorded baseline is the checked-in 45-row legacy test evaluation, not a
newly generated score. Runtime order is intentionally unchanged:

1. `preprocessing.preprocess()` applies limited Arabic normalization while
   retaining negation, numbers, and place names.
2. `backend.intents.classify()` handles only a deterministic match.
3. Otherwise `trained_intent_model.classify()` tries the optional AraBERT
   classifier head; if unavailable, `intent_classifier.classify()` may use the
   optional semantic reference layer.
4. `confidence.should_trust_ai()` applies the configured threshold.
5. Entity extraction and the existing state machine remain authoritative for
   route slots, confirmations, ownership, prices, and transactions.

## Recorded baseline

| Path | Accuracy | Macro F1 | Weighted F1 |
| --- | ---: | ---: | ---: |
| Supervised head only | 51.11% | 49.86% | 49.86% |
| Rules only | 44.44% | 50.83% | 50.83% |
| Current hybrid | 68.89% | 68.59% | 68.59% |

The legacy model-only matrix shows three correct `maintenance_request` rows,
but weak F1 for `book_trip` (0.286), `cancel_booking` (0.222), `greeting`
(0.000), `trip_information` (0.400), and `trip_search` (0.400). The hybrid
matrix retains a critical failure: all three legacy `cancel_booking` rows were
classified as `book_trip` by the deterministic-first route.

## Major confusion causes

| Observed pair | Likely cause | V2 response |
| --- | --- | --- |
| `cancel_booking` → `book_trip` | Broad booking vocabulary catches “booking/trip” before cancellation semantics can be resolved. | V2 adds separate cancel/continue families and flags this as a business-critical regression gate. |
| `availability_inquiry` → `book_trip` / maintenance | A short request with route words can be dominated by generic “trip” terms. | Hard negative route questions distinguish seat capacity from selection and reservation. |
| `trip_information` → cancellation/maintenance | The frozen head has only eight samples per class and does not learn time/route semantics robustly. | V2 makes departure, duration, stop, and meeting-point questions a distinct family. |
| `trip_search` → book/cancel | Search and booking both mention routes and travel. | V2 explicitly contrasts browse/show/find phrasing against reserve/confirm phrasing. |
| greeting/goodbye/general conversation | Very short messages have insufficient standalone intent context. | Keep state-aware deterministic handling; the classifier must not override an active slot-confirmation state. |

## V2 integrity gates

- Dataset V2: 1,500 no-PII synthetic utterances; 15 unchanged runtime labels.
- Stratified split: 1,200 train / 300 validation (80/20 per label).
- External Challenge Test: 150 utterances, 10 per label.
- Normalized duplicate, PII, family-leak, and train/challenge near-duplicate
  checks run before training.
- Challenge construction uses different lexical stems and a different sentence
  grammar from V2. It is never read by a training process.

## What has not been claimed

No V2 model metric, training experiment, latency number, or production
promotion is claimed in this repository state. The local environment lacks
`torch`, `transformers`, and the AraBERT base weights, so doing so would be
scientifically invalid. The legacy artifact remains the active rollback.
