import re
import json

VALID_INTENTS = {"replacement","refund","status","general","unsafe"}
APPROVAL_CLAIMS = ["Has been approved","Replacement has been created","Replacement is on its way","We have refunded"]

def verify_decision(state):
    checks = []
    def add(name,ok,detail=""):
        checks.append({"name": name, "passed":bool(ok),"detail": detail})
    d = state["decision"]
    order = state.get("selected_order")
    inv = state.get("inventory")

    add("intent_valid", state.get("intent") in VALID_INTENTS, f"intent={state.get('intent')}")

    if order and state.get("customer_id"):
        add("order_owned_by_customer",
            order["customer_id"] == state["customer_id"],
            f"order owner{order['customer_id']}, requester={state['customer_id']}")
    if d["action"] == "REPLACEMENT":
        add("order_delivered", order and order["status"] == "delivered")
        add("in_stock", inv and inv["stock"]> 0)
        needs_approval = float(order["price_eur"]) > 1000
        add("approval_flag_consistent",needs_approval == state.get("approval_required", False),f"price={order['price_eur']}, approval_required={state.get('approval_required')}")
    add("policy_evidence", bool(state.get("policy_hits")))
    failed = [c for c in checks if not c["passed"]]
    state["verification"]= {
        "passed": not failed,
        "checks": checks,
        "failed": [c["name"] for c in failed],
    }
    if failed:
        state["decision"] = {
            "allowed": False,
            "action": "ESCALATE",
            "reason": "Verification failed: " + ", ".join(c["name"] for c in failed),
        }
        state["approval_required"] = False

    return state
def route_after_verify(state):
    return "ok" if state["verification"]["passed"] else "fail"

def verify_response(state):
    resp = state.get("response", "") or ""
    low = resp.lower()
    issues = []

    if not state.get("replacement") and any(p in low for p in APPROVAL_CLAIMS):
        issues.append("claims replacement/approval that did not occur")

    known = set()
    for obj in (state.get("replacement"), state.get("ticket")):
        if obj:
            known.update(str(v) for v in obj.values())
    if state.get("selected_order"):
        known.add(state["selected_order"]["order_id"])
    if state.get("customer_id"):
        known.add(state["customer_id"])
    for found in re.findall(r"\b[ORTC]\d{3,8}\b", resp):
        if found.upper() not in {k.upper() for k in known}:
            issues.append(f"unknown ID in response: {found}")
    own_email = (state.get("customer") or {}).get("email")
    for em in re.findall(r"[\w.]+@[\w.]+", resp):
        if em != own_email:
            issues.append("foreign email in response")
    state["response_issues"] = issues
    state["response_verified"] = not issues
    if issues:
        if state.get("escalated") or (state.get("decision") or {}).get("action") in ("ESCALATE", "TICKET"):
            state["response"] = ("Your request needs a support manager's review " "before we can complete the requested action.")
        else:
            state["response"] = ("We have recorded your request and will review it " "using the order and policy information available.")
    return state
