import json
from pathlib import Path

PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "dermarag_skin_rules_v0_2.json"
)
data = json.loads(PATH.read_text(encoding="utf-8"))
rules = data["rules"]
profiles = data["skin_profiles"]

ids = [r["rule_id"] for r in rules]
assert len(ids) == len(set(ids)), "duplicate rule_id"

canon = {r["canonical_group"] for r in rules}
refs = set()
for p in profiles:
    refs.update(p.get("helpful_function_groups", []))
    refs.update(p.get("caution_function_groups", []))
missing = sorted(refs - canon)
assert not missing, f"profile references missing canonical groups: {missing}"

# exact alias collisions are allowed only when consciously reviewed.
seen = {}
collisions = {}
for r in rules:
    for alias in r.get("aliases", []):
        key = " ".join(alias.casefold().split())
        if key in seen and seen[key] != r["rule_id"]:
            collisions.setdefault(key, {seen[key]}).add(r["rule_id"])
        else:
            seen[key] = r["rule_id"]

# known intentional cross-function aliases
allowed = {"베타-글루칸", "beta-glucan"}
unexpected = {k: sorted(v) for k, v in collisions.items() if k not in allowed}
assert not unexpected, f"unexpected alias collisions: {unexpected}"

volatile = next(r for r in rules if r["rule_id"] == "volatile_alcohol")
fatty = next(r for r in rules if r["rule_id"] == "fatty_alcohol_emollient")
assert "alcohol" not in {a.casefold() for a in volatile["aliases"]}
assert "cetearyl alcohol" in {a.casefold() for a in fatty["aliases"]}
assert "talc" in seen and "alumina" in seen
print(f"OK: {len(rules)} rules, {len(seen)} normalized aliases, {len(profiles)} profiles")
