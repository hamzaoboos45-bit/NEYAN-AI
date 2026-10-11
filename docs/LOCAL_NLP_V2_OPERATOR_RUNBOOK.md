# Local Windows operator runbook — NEYAN NLP V2

V1 remains the runtime default. These commands train and evaluate V2 locally;
they do not alter V1 and do not permit challenge data in training.

```powershell
# From the NEYAN_AI project root, using Python 3.11.
py -3.11 -m venv .venv-nlp-v2
.\.venv-nlp-v2\Scripts\Activate.ps1
$env:PYTHONUTF8 = "1"
python -m pip install --upgrade pip
python -m pip install flask pytest numpy torch transformers
python -c "import sys, torch, transformers, flask, pytest; print(sys.version); print(torch.__version__); print(transformers.__version__); print('cuda=', torch.cuda.is_available())"
```

## Validate data only

```powershell
python training_data\build_dataset_v2.py
python scripts\train_chat_model_v2.py --validate-only
python -m unittest tests.test_chat_nlp_dataset_v2 -v
```

## Validation-only experiment selection

Do **not** run the evaluator in this step. Select a configuration from
validation Macro F1 across the three fixed seeds only.

```powershell
$seeds = 20260920,20260921,20260922
foreach ($seed in $seeds) {
  python scripts\train_chat_model_v2.py --seed $seed --unfreeze-last-layers 0 --max-length 96 --batch-size 16 --head-learning-rate 0.003 --output-dir "artifacts\v2-head-$seed"
  python scripts\train_chat_model_v2.py --seed $seed --unfreeze-last-layers 2 --max-length 96 --batch-size 8 --encoder-learning-rate 0.00002 --output-dir "artifacts\v2-unfreeze2-$seed"
  python scripts\train_chat_model_v2.py --seed $seed --unfreeze-last-layers 4 --max-length 96 --batch-size 8 --encoder-learning-rate 0.00002 --output-dir "artifacts\v2-unfreeze4-$seed"
}
```

Review only each produced metadata file's `validation_metrics`. Choose the
configuration by mean validation Macro F1, standard deviation, and critical
intent F1; do not inspect Challenge results while choosing.

## Install the selected V2 candidate and evaluate external tests

Replace the placeholder path below only after validation selection. This
copies a V2 candidate alongside V1; it does not activate V2 in production.

```powershell
$winner = "artifacts\v2-head-20260920" # replace after validation-only selection
Copy-Item "$winner\arabert_intent_delta_v2.pt" "backend\nlp\models\arabert_intent_delta_v2.pt" -Force
Copy-Item "$winner\chat_intent_metadata_v2.json" "backend\nlp\models\chat_intent_metadata_v2.json" -Force

# Evaluator explicitly loads V2 regardless of the production default.
python scripts\evaluate_chat_model_v2.py --output docs\CHAT_MODEL_EVALUATION_V2.json
```

The evaluator writes model-only, rules-only, and hybrid metrics, per-class
reports, confusion matrices, confidence summaries, and misclassified examples
for both legacy and Challenge tests. It fails rather than evaluating V1 if V2
is missing or invalid.

## Tests and controlled promotion

```powershell
python -m pytest tests\test_trained_intent_model_versions.py tests\test_chat_nlp_dataset_v2.py tests\test_chat_model_training.py -q
python -m pytest -q

# Only after all review gates pass, set this in local deployment configuration.
# Default remains v1 until this deliberate promotion.
$env:TRAINED_CHAT_MODEL_VERSION = "v2"
python -c "from backend.nlp import trained_intent_model as m; print('v2 available=', m.is_available('v2')); print('error=', m.load_error('v2'))"
```

Promotion gate: V2 must beat V1 on legacy and Challenge metrics, have no
critical intent F1 below 0.70 without written justification, and pass full
regression. If any gate fails, leave `TRAINED_CHAT_MODEL_VERSION=v1`; V1 files
remain the rollback artifact.
