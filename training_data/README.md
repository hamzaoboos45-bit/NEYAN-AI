# NEYAN Chat intent dataset

`chat_intents.jsonl` is generated deterministically from `build_dataset.py`.
Every row has `text`, `intent`, and an explicit `split` (`train`,
`validation`, or `test`). The utterances are synthetic Arabic, Jordanian
Arabic, English, and a small amount of code-switched text; they contain no
customer names, contact details, booking identifiers, credentials, or logs.

The labels are exactly the active canonical labels in
`backend/nlp/intent_classifier.py`. There are intentionally no independent
`forming_trip` or `review` labels: the current state machine reaches the
forming-trip fallback after a deterministic trip search and has no review
conversation workflow. Training data must not invent product capabilities.

Run `python training_data/build_dataset.py` after changing the reviewed source
examples, then run `python scripts/train_chat_model.py` to validate, train,
and evaluate the compact supervised classifier.
