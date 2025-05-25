# explainer.py
import os
import json
import requests
import yaml
from typing import Dict, Any, List

def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Load olama_url & olama_model from YAML."""
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

class OlamaExplainer:
    """
    Connect to Olama and generate JSON feedback for each survived mutant record.
    Expects records with keys:
      - mutant_name (str)
      - source_file (str)
      - mutation_desc (str)
      - tests: List[{test_name, test_code}]
    Returns a dict with: why, fix, example_test.
    """
    def __init__(self, config_path: str = "config.yaml"):
        cfg = load_config(config_path)
        self.olama_url = cfg.get("olama_url", "http://localhost:11434/v1/chat/completions") # default Olama URL everyone uses this localhost
        self.model    = cfg.get("olama_model", "codellama-7b")
        self.headers  = {"Content-Type": "application/json"}
        self._cache: Dict[str, Dict[str, str]] = {}

    def explain(self, rec: Dict[str, Any]) -> Dict[str, str]:
        key = rec["mutant_name"]
        if key in self._cache:
            return self._cache[key]

        # Build prompt
        prompt = (
            "You are a mutation‐testing expert. Reply ONLY in JSON with keys: why, fix, example_test.\n\n"
            f"Mutation description: {rec['mutation_desc']}\n"
            f"File: {rec['source_file']}\n"
        )
        tests = rec.get("tests", [])
        if tests:
            prompt += "Existing tests that touch this code path:\n"
            for t in tests[:2]:
                # show name and first line of code
                line = t.get("test_code", "").splitlines()[0]
                prompt += f"- {t['test_name']}: {line}...\n"
        else:
            prompt += "No existing tests cover this code path.\n"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user",   "content": prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 200
        }
        resp = requests.post(self.olama_url, headers=self.headers, json=payload)
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()

        # parse JSON or fall back to inner JSON block
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            s, e = raw.find("{"), raw.rfind("}")
            obj = json.loads(raw[s:e+1])

        out = {
            "why":          obj.get("why", ""),
            "fix":          obj.get("fix", ""),
            "example_test": obj.get("example_test", "")
        }
        self._cache[key] = out
        return out

def main(
    input_path:  str = "mutants/survived_mutants.json",
    output_path: str = "mutants/survived_mutants_with_explanations.json"
) -> None:
    if not os.path.exists(input_path):
        raise FileNotFoundError(input_path)

    records: List[Dict[str, Any]] = json.loads(open(input_path, 'r').read())
    expl = OlamaExplainer()
    for rec in records:
        fb = expl.explain(rec)
        rec.update(fb)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    main()
