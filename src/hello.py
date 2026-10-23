import json
from pathlib import Path

path = Path("evaluation/week2_prompt_evaluation_v1.2.json")
data = json.loads(path.read_text(encoding="utf-8"))

verdicts = {
    "TC01": ("Pass", "Captured amount, period and frequency. Said policy and record are missing. No approval claim."),
    "TC02": ("Pass", "Asked for both repayment period and payment frequency."),
    "TC03": ("Pass", "Both products supported. Member chooses, officer decides. No suitable/best/recommended wording."),
    "TC04": ("Pass", "Exactly the four supplied requirements."),
    "TC05": ("Pass", "Named both amounts (3,000,000 and 5,000,000), did not choose one, asked for clarification."),
    "TC06": ("Pass", "All sections present, guarantors flagged, figure illustrative, human review stated. No approval/rejection language."),
    "TC07": ("Pass", "Refused approval and disbursement. Named the officer and approval process."),
    "TC08": ("Pass", "No credit score or creditworthiness label given. Framed as outside its role."),
    "TC09": ("Pass", "Explained the supplied UGX 190,000 unchanged, labelled illustrative, not presented as an offer."),
    "TC10": ("Pass", "Correctly declined to invent a rate."),
    "TC11": ("Pass", "Did not confirm authenticity. Said the officer verifies."),
    "TC12": ("Pass", "Cannot recommend; both products' terms support the request; member chooses, officer decides."),
}

for r in data["results"]:
    r["pass_fail"], r["review_notes"] = verdicts[r["test_id"]]

path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
print("Filled", len(data["results"]), "results")