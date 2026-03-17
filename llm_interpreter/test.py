from shap_llm_builder import build_combined_llm_payload_from_db
import json

payload = build_combined_llm_payload_from_db("005930")
print(json.dumps(payload, ensure_ascii=False, indent=2))