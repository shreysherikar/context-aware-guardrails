# Open-source training sources (defensive classifier only)

This project trains a prompt-intent classifier on **user requests**, not on
exploit payloads, malware binaries, or attack how-tos.

| Source | License | Use |
| --- | --- | --- |
| [CySecBench](https://github.com/cysecbench/dataset) | MIT | Cyber-attack solicitation prompts (12k) |
| [JailbreakBench JBB-Behaviors](https://huggingface.co/datasets/JailbreakBench/JBB-Behaviors) | MIT | Harmful/benign behaviors; cyber/privacy/fraud only |
| [AdvBench harmful behaviors](https://github.com/llm-attacks/llm-attacks) | MIT | Cyber-keyword subset of harmful goals |
| [Stanford Alpaca](https://github.com/tatsu-lab/stanford_alpaca) | CC BY-NC 4.0 | Benign instruction prompts (negative class) |
| [Databricks Dolly 15k](https://huggingface.co/datasets/databricks/databricks-dolly-15k) | CC BY-SA 3.0 | Extra benign instructions |
| `data/offensive_cyber_prompts.csv` | this repo | Hand-labeled seed (unsafe + safe) |
| Paraphrase wrappers | this repo | Request-style rewrites of the same labeled asks (full unique set, ~393k rows) |

Retrain:

```bash
uv pip install scikit-learn
uv run python scripts/train_offensive_classifier.py
```
