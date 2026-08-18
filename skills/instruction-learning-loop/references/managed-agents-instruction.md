## Origin-aware instruction learning

- An error or roadblock found by the agent qualifies for durable instruction-learning only after the root cause is established and the fix is freshly verified. Expected probes, test-driven-development red phases, and one-off failures do not qualify.
- When the user reports an error after delivery, remediate it end-to-end, but agent verification remains provisional: do not claim user-observed resolution or finalize instruction learning until the user explicitly confirms the issue is resolved in later testing. Any later user report supersedes the active agent-origin learning cycle.
