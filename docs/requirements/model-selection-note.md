# Model Selection Note — SACCO Member-Case Preparation Agent


## Model Selection Decision

The group will use **Google Gemini 3.8 Flash (`gemini-3.8-flash`)** as the initial model for the SACCO Member-Case Preparation Agent baseline.

Gemini 3.8 Flash was selected because it is a current Flash model designed for **long-horizon tasks, agentic tool use, and complex multi-step workflows**, which aligns well with the planned direction of the SACCO agent. The model provides API access for application integration and is available on a **free tier**, making it suitable for a student project with a strong preference for keeping development costs at zero.

According to Google's current Gemini API pricing information, Gemini 3.8 Flash has a **free tier with no charge for input or output tokens**. If the paid tier is required, the current standard price is **$0.75 per 1 million input tokens and $3.75 per 1 million output tokens through December 31, 2026** (rising to $1.50 / $7.50 from January 1, 2027).

## Evaluation Against Criteria

- **Capability:** Suitable for the baseline's needs — understanding policy instructions, following constraints, explaining procedures, and producing structured responses. Its agentic/multi-step support also gives a foundation for later RAG and agent work, though that is outside this baseline's scope.
- **Cost:** Free tier covers development and testing within free-tier limits, matching the project's zero-cost priority. A small budget is available if paid usage later becomes necessary, but is not required for the baseline.
- **Latency:** Not assumed from provider marketing. The team will measure actual response time on representative SACCO prompts during baseline testing and record the observed results.
- **Privacy:** The project uses only synthetic member records and public/team-created policy documents. Google's documentation states free-tier content may be used to improve its products, while the paid tier is not used this way — so no real member data will be submitted at any point.
- **Access:** Available via Google's API, allowing direct integration into the application rather than relying on the AI Studio chat interface alone.

## Evaluation Approach

The model will be tested against the project's 10-case prompt evaluation set, covering instruction-following, procedure explanation, handling incomplete information, refusing staff-only decisions, respecting AI/system/human boundaries, output format, and avoidance of fabricated information. Expected behaviour is defined before testing; actual behaviour is then recorded and marked pass/fail. The model is only accepted as baseline if it performs adequately — if important cases fail, the prompt will be revised and retested, and if failures persist, an alternative model will be evaluated with the reason documented. This keeps the selection evidence-based rather than assumed from advertised capabilities.
