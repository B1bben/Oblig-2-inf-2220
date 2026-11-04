from agent.llm import classify_request
from rag.retrieve import retrieve
from tools.business_tools import log_audit
from agent.verification import RECOVERABLE


def reflect_on_decision(state):
    attempt = state.get("decision_attempts", 0) + 1
    state["decision_attempts"] = attempt
    failed = state["verification"]["failed"]
    actions = sorted({RECOVERABLE[f] for f in failed if f in RECOVERABLE})
    entry = {
        "stage": "decision",
        "attempt": attempt,
        "failed": failed,
        "actions": actions,
    }

    if "reclassify" in actions:
        feedback = (
            f"Your previous answer '{state.get('intent')}' is not an allowed intent. "
            "Choose exactly one of: replacement, refund, status, general, unsafe."
        )
        r = classify_request(state["user_text"], feedback=feedback)
        entry["intent_before"], entry["intent_after"] = (
            state.get("intent"),
            r.get("intent"),
        )
        state["intent"], state["confidence"] = r.get("intent"), r.get("confidence", 0.0)

    if (
        "re_retrieve" in actions
    ):  # runs after reclassify, so it uses the corrected intent
        order = state.get("selected_order") or {}
        q = (
            f"{state.get('intent', '')} policy for {order.get('status', 'unknown')} "
            f"{order.get('product_name', '')} order"
        )
        state["retrieval_query"] = q
        state["policy_hits"] = retrieve(q, 2 + attempt)
        entry["retrieved"] = [h["source"] for h in state["policy_hits"]]

    state.setdefault("reflection_log", []).append(entry)
    log_audit(
        state.get("customer_id") or "UNKNOWN",
        "REFLECTION_RETRY",
        f"decision attempt {attempt}",
        entry,
    )
    return state
