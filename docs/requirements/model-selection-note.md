# Model Selection Note — SACCO Member-Case Preparation Agent

## Model Selection Decision

The group selected Google Gemini 3.6 Flash (`gemini-3.6-flash`) as the baseline model for the SACCO Member-Case Preparation Agent.

The group initially tested Gemini 3.8 Flash and Gemini 3.7 Flash, but both produced repeated `503 Service Unavailable` errors during baseline integration testing, including after retry and exponential-backoff handling. The team therefore selected Gemini 3.6 Flash as the primary baseline based on the observed availability during testing and its suitability for the project. Google lists Gemini 3.6 Flash as a stable model and describes it as a Flash model balancing speed and multimodal capabilities for general agentic and everyday tasks.

## Evaluation Against Selection Criteria

**Capability:** Gemini 3.6 Flash supports text, image, video, audio and PDF inputs, with text output. It supports function calling, code execution, file search and structured outputs, which provide a suitable foundation for the project's later RAG, tool-use and agent functionality. It has a 1,048,576-token input limit and 65,536-token output limit.

**Cost:** Gemini 3.6 Flash currently has a free tier with no charge for input or output tokens. Paid standard pricing is $0.75 per 1 million input tokens and $3.75 per 1 million output tokens through December 31, 2026, increasing to $1.50 and $7.50 respectively from January 1, 2027.

**Latency/Reliability:** The team measures actual response time and availability rather than relying on provider claims. Transient 503 errors, like those observed during initial testing of Gemini 3.7/3.8 Flash, are documented by Google as errors for which retry/backoff can be used.

**Privacy:** The project uses only synthetic member records and public/team-created policy documents. No real member or sensitive financial information will be submitted during development.

**Access:** The model is available through the Gemini API, allowing direct integration into the application rather than relying only on the AI Studio interface. The stable model ID is `gemini-3.6-flash`.

## Evaluation Approach

The selected model will be evaluated using the project's 10-case prompt evaluation set. Tests will cover instruction following, procedure explanation, incomplete information, staff-only decisions, AI/System/Human boundaries, output format and avoidance of fabricated information. Expected behaviour will be defined before testing, followed by recording actual behaviour and pass/fail results.

If important failures occur, the prompt will be revised and retested. If the model continues to perform inadequately, an alternative model will be evaluated and the reason documented. This provides an evidence-based basis for the final model selection. (Source: Google Gemini API model and pricing documentation, checked September 2026.)
