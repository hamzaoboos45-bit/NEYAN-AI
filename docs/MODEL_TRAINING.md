# NEYAN chat-model training

## Architecture and data

The production path remains hybrid: deterministic high-signal rules run first;
only unresolved utterances are passed to the supervised AraBERT intent head.
Entity extraction remains the existing deterministic governorate/date/time and
service parser. The model never receives authority to choose a trip, price,
seat count, booking owner, company, maintenance status, or review eligibility.

The original optional semantic backbone is
`aubmindlab/bert-base-arabertv02` with its matching `AutoTokenizer`. The
fine-tuned deployable delta is `backend/nlp/models/arabert_intent_delta.pt`.
It contains only the classifier-head state; the public base model is acquired
through the existing Transformers configuration when available. If either the
dependency, base model, or delta cannot load, the application safely falls
back to the pre-existing semantic/rule path.

The reviewed synthetic set is `training_data/chat_intents.jsonl`, generated
from `training_data/build_dataset.py`. It contains 195 no-PII samples across
the current 15 labels: greeting, goodbye, book_trip, cancel_booking,
trip_search, trip_information, company_information, maintenance_request,
complaint, help, price_inquiry, availability_inquiry, confirmation,
cancellation, and general_conversation. Split sizes are 120/30/45
(train/validation/test), with 8/2/3 examples per label. It includes Arabic,
Jordanian Arabic, English, and controlled code switching. No standalone
forming-trip or review labels are invented because the current Chat state
machine has no such independent intent handlers.

## Reproduction

Run, from the project root:

```text
python training_data/build_dataset.py
python scripts/train_chat_model.py
python scripts/evaluate_chat_model.py --output docs/CHAT_MODEL_EVALUATION.json
```

The fixed seed is `20260920`. CPU is the tested device. The selected experiment
freezes AraBERT and fine-tunes its randomly initialized classification head;
the training command uses a batch size of 16, maximum length of 64, AdamW,
head learning rate 0.005, at most 60 epochs, and patience 8. Best epoch is
selected by validation Macro F1, never by the frozen test set.

## Measured result

The first full-last-layer experiment was rejected: validation Macro F1 reached
only 0.145 and CPU cost was disproportionate. The selected head-only run
stopped after 16 epochs; best epoch was 8 (validation Macro F1 0.4763), total
training time 4.95 seconds on the tested CPU. Its held-out model-only result
was Accuracy 0.5111, Macro F1 0.4986, Weighted F1 0.4986; this is not used as
the production comparison because production retains rules first.

On the frozen 45-row test set, the actual prior rule-only path measured:

- Accuracy 0.4444; Macro F1 0.5083; Weighted F1 0.5083.

The integrated rules-first / fine-tuned-second path measured:

- Accuracy 0.6889; Macro F1 0.6859; Weighted F1 0.6859.

The post-load single-message full-model benchmark was 95.34 ms per held-out
message in this CPU environment. Metrics and full per-class confusion matrices
are retained in `docs/CHAT_MODEL_TRAINING_METRICS.json` and
`docs/CHAT_MODEL_EVALUATION.json`.

## Known limits

The dataset is intentionally small and synthetic, so it cannot prove real-user
coverage. The main residual confusions are closely related trip booking/search
and social short utterances. Confirmation/cancellation still require the
existing exact state-aware deterministic checks; a model intent is never an
authorization. Add only reviewed, non-PII examples and preserve split-family
separation before retraining.
