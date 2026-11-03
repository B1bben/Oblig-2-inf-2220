# Instructor Notes

## Core teaching point

This project intentionally separates:
1. LLM language generation
2. deterministic business tools
3. retrieval
4. orchestration
5. authorization
6. execution
7. evaluation

The LLM should not be treated as the database, policy engine, or authorization system.

## Suggested live demo

1. Run the damaged-laptop request for C001/O1001.
2. Show policy retrieval.
3. Show that EUR 1299 exceeds the approval threshold.
4. Run once without approval: the agent escalates.
5. Run with human approval: a replacement action is created.
6. Open the audit log.
7. Try O1004: the order is still shipped, so replacement is not automatically created.
8. Try a privacy request: the agent refuses/escalates.

## Discussion questions

- What if the LLM hallucinates a customer ID?
- Should the LLM be allowed to write SQL?
- What actions need approval?
- What happens if the vector database is unavailable?
- How would you test prompt injection?
- Which metrics matter to a business owner?
