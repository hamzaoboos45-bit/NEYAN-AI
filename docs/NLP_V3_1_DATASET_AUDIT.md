# NEYAN NLP V3.1 Dataset Audit

## Scope

This audit covers only `training_data/chat_intents_v3_1.jsonl`. It does not open, hash, compare, or otherwise inspect the sealed Final Holdout. The Final Holdout remains an operator-controlled, post-selection evaluation set.

## Result

- Total rows: 3450
- Train / validation: 3000 / 450
- Intent taxonomy: 15 labels
- Normalized duplicate count: 0
- Family ownership: strict; a family belongs to exactly one split.

| Intent | Train rows | Validation rows | Train families | Validation families | Duplicates | Family overlap |
|---|---:|---:|---:|---:|---:|---:|
| availability_inquiry | 200 | 30 | 10 | 3 | 0 | 0 |
| book_trip | 200 | 30 | 10 | 3 | 0 | 0 |
| cancel_booking | 200 | 30 | 10 | 3 | 0 | 0 |
| cancellation | 200 | 30 | 10 | 3 | 0 | 0 |
| company_information | 200 | 30 | 10 | 3 | 0 | 0 |
| complaint | 200 | 30 | 10 | 3 | 0 | 0 |
| confirmation | 200 | 30 | 10 | 3 | 0 | 0 |
| general_conversation | 200 | 30 | 10 | 3 | 0 | 0 |
| goodbye | 200 | 30 | 10 | 3 | 0 | 0 |
| greeting | 200 | 30 | 10 | 3 | 0 | 0 |
| help | 200 | 30 | 10 | 3 | 0 | 0 |
| maintenance_request | 200 | 30 | 10 | 3 | 0 | 0 |
| price_inquiry | 200 | 30 | 10 | 3 | 0 | 0 |
| trip_information | 200 | 30 | 10 | 3 | 0 | 0 |
| trip_search | 200 | 30 | 10 | 3 | 0 | 0 |

## Design checks

- Each intent has 10 independently authored training families of 20 examples each.
- Each intent has 3 validation-only families of 10 examples each.
- Train and validation family identifiers are split-owned and never overlap.
- Price, discovery, trip details, seat availability, and booking use deliberately contrasting semantic contracts while retaining realistic lexical overlap.
- Confirmation and cancellation remain in the corpus, but the chatbot must give its deterministic conversation-state handling priority whenever it is awaiting confirmation or cancellation.
- Runtime audit: `backend/chatbot.py` checks `intents.is_cancellation()` and then `intents.is_confirmation()` inside booking, maintenance, and Forming Trip finalizers before any write operation; a non-answer remains in the pending state.

## Sealed Final Holdout

No byte-level comparison is performed here because the task expressly forbids inspecting the sealed file. A byte-for-byte immutability check requires a trusted baseline checksum supplied by the holdout custodian; this report neither derives nor changes that checksum.
