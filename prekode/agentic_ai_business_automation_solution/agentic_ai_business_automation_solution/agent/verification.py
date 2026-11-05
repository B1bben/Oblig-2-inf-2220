import re
from agent.prompt_injection_defense import scan
from tools.business_tools import log_audit, REFUND_AUTO_LIMIT_EUR

VALID_INTENTS = {"replacement", "refund", "status", "general", "unsafe"}
ID_RE = re.compile(r"\b[ORTC]\d{3,8}\b")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
REQUIRED_POLICY = {
    "REPLACEMENT": {"return_policy", "warranty_policy", "shipping_policy"},
    "REFUND": {"return_policy"},
}
APPROVAL_CLAIMS = [
    "has been approved",
    "replacement has been created",
    "replacement is on its way",
    "we have refunded",
]
MAX_DECISION_RETRIES = 2
MAX_RESPONSE_ATTEMPTS = 3
RECOVERABLE = {"intent_valid": "reclassify", "policy_evidence": "re_retrieve"}


def verify_decision(state):
    checks = []

    def add(name, ok, detail=""):
        checks.append({"name": name, "passed": bool(ok), "detail": detail})

    d = state["decision"]
    order = state.get("selected_order")
    inv = state.get("inventory")

    add(
        "intent_valid",
        state.get("intent") in VALID_INTENTS,
        f"intent={state.get('intent')}",
    )

    inj = scan(state.get("user_text", ""))
    state["injection_flags"] = inj
    add("no_prompt_injection", not inj, ",".join(inj))
    owner_ok = True
    if order:
        requester = state.get("customer_id")
        owner_ok = requester is not None and order["customer_id"] == requester
        add(
            "order_owned_by_customer",
            owner_ok,
            f"order owner{order['customer_id']}, requester={state['customer_id']}",
        )
        if not owner_ok:
            state["blocked_order_id"] = order["order_id"]
            state["selected_order"] = None
            state["inventory"] = None
    invoice = state.get("invoice")
    if (
        invoice
        and state.get("customer_id")
        and invoice["customer_id"] != state["customer_id"]
    ):
        add(
            "invoice_owned_by_customer",
            False,
            f"invoice owner={invoice['customer_id']}",
        )
        state["invoice"] = None
        invoice = None
    if d["action"] == "REFUND" and owner_ok and invoice:
        add("refund_invoice_paid", invoice["status"] == "paid")
        add(
            "refund_amount_valid",
            0
            < float(invoice["amount_eur"])
            <= float(order["price_eur"]) * order.get("quantity", 1),
        )
        add(
            "refund_approval_consistent",
            (float(invoice["amount_eur"]) > REFUND_AUTO_LIMIT_EUR)
            == state.get("approval_required", False),
        )
    if d["action"] == "REPLACEMENT" and owner_ok:
        add("order_delivered", order and order["status"] == "delivered")
        add("in_stock", inv and inv["stock"] > 0)
        needs_approval = float(order["price_eur"]) > 1000
        add(
            "approval_flag_consistent",
            needs_approval == state.get("approval_required", False),
            f"price={order['price_eur']}, approval_required={state.get('approval_required')}",
        )
    hits = state.get("policy_hits") or []
    sources = {h["source"] for h in hits}
    required = REQUIRED_POLICY.get(d["action"])
    if required:
        add(
            "policy_evidence",
            bool(sources & required),
            f"retrieved={sorted(sources)}, required_any_of={sorted(required)}",
        )
    else:
        add("policy_evidence", bool(hits), f"retrieved={sorted(sources)}")
    failed = [c for c in checks if not c["passed"]]
    state["verification"] = {
        "passed": not failed,
        "checks": checks,
        "failed": [c["name"] for c in failed],
    }

    return state


def route_after_verify(state):
    v = state["verification"]
    if v["passed"]:
        return "ok"
    hard = set(v["failed"]) - RECOVERABLE.keys()
    if hard or state.get("decision_attempts", 0) >= MAX_DECISION_RETRIES:
        return "escalate"
    return "reflect"


def escalate_after_verify(state):
    # Moved here from verify_decision: only runs once retries are exhausted
    # or a hard check failed.
    if state.get("injection_flags"):
        state["intent"] = "unsafe"
    state["decision"] = {
        "allowed": False,
        "action": "ESCALATE",
        "reason": "Verification failed: " + ", ".join(state["verification"]["failed"]),
    }
    state["approval_required"] = False
    return state


def verify_response(state):
    resp = state.get("response", "") or ""
    low = resp.lower()
    issues = []

    if (
        not state.get("replacement")
        and not state.get("refund")
        and any(p in low for p in APPROVAL_CLAIMS)
    ):
        issues.append("claims replacement/approval that did not occur")

    known = set()
    for obj in (state.get("replacement"), state.get("ticket"), state.get("refund")):
        if obj:
            known.update(str(v) for v in obj.values())
    if state.get("selected_order"):
        known.add(state["selected_order"]["order_id"])
    if state.get("customer_id"):
        known.add(state["customer_id"])
    known_upper = {k.upper() for k in known}
    for found in ID_RE.findall(resp):
        if found.upper() not in known_upper:
            issues.append(f"unknown ID in response: {found}")
    own_email = ((state.get("customer") or {}).get("email") or "").lower()
    for em in EMAIL_RE.findall(resp):
        if em.lower() != own_email:
            issues.append("foreign email in response")
    state["response_issues"] = issues
    state["response_verified"] = not issues
    if issues:
        log_audit(
            state.get("customer_id") or "UNKNOWN",
            "RESPONSE_REJECTED",
            f"Generated response failed verification (attempt {state.get('response_attempts', 0)})",
            {"issues": issues},
        )

    return state


def route_after_response(state):
    if state.get("response_verified"):
        return "ok"
    if state.get("response_attempts", 0) >= MAX_RESPONSE_ATTEMPTS:
        return "fallback"
    return "retry"


def fallback_response(state):
    # Moved from verify_response: only used once every attempt has been rejected.
    if state.get("escalated") or (state.get("decision") or {}).get("action") in (
        "ESCALATE",
        "TICKET",
    ):
        state["response"] = (
            "Your request needs a support manager's review "
            "before we can complete the requested action."
        )
    else:
        state["response"] = (
            "We have recorded your request and will review it "
            "using the order and policy information available."
        )
    log_audit(
        state.get("customer_id") or "UNKNOWN",
        "RESPONSE_FALLBACK",
        f"Canned response used after {state.get('response_attempts', 0)} rejected attempts",
        {"last_issues": state.get("response_issues")},
    )
    return state
