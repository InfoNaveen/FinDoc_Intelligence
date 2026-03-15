"""
STEP 3: Review and finalize submission.json
Run: python gauntlet/generate_submission.py
"""

import json
from collections import Counter

with open("submission.json") as f:
    data = json.load(f)

findings = data["findings"]
print(f"Team: {data['team_id']}")
print(f"Total findings: {len(findings)}")
print()

cats = Counter(f["category"] for f in findings)
print("Category breakdown:")
for cat, count in sorted(cats.items()):
    print(f"  {cat:35s} {count}")

print()
print("First 5 findings preview:")
for f in findings[:5]:
    print(f"  {f['finding_id']} | {f['category']} | {f['document_refs']} | {f['reported_value']} → {f['correct_value']}")

print()
print("submission.json is ready to submit.")
