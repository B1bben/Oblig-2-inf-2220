import re
import json
from agent.prompt_injection_defense import scan
from tools.business_tools import log_audit
VALID_INTENTS = {"replacement","refund","status","general","unsafe"}
ID_RE = re.compile(r"\b[ORTC]\d{3,8}\b")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
REQUIRED_POLICY = {"REPLACEMENT": {"return_policy", "warranty_policy", "shipping_policy"},}
APPROVAL_CLAIMS = ["has been approved","replacement has been created","replacement is on its way","we have refunded"]

def verify_decision(state):
    checks = []
    def add(name,ok,detail=""):
        checks.append({"name": name, "passed":bool(ok),"detail": detail})
    d = state["decision"]
    order = state.get("selected_order")
    inv = state.get("inventory")

    add("intent_valid", state.get("intent") in VALID_INTENTS, f"intent={state.get('intent')}")

    inj = scan(state.get("user_text", ""))
    state["injection_flags"] = inj
    add("no_prompt_injection", not inj, ",".join(inj))
    owner_ok = True
    if order:
        requester = state.get("customer_id")
        owner_ok = requester is not None and order["customer_id"] == requester
        add("order_owned_by_customer", owner_ok,
            f"order owner{order['customer_id']}, requester={state['customer_id']}")
        if not owner_ok:
            state["blocked_order_id"] = order["order_id"]
            state["selected_order"] = None
            state["inventory"] = None
    if d["action"] == "REPLACEMENT" and owner_ok:
        add("order_delivered", order and order["status"] == "delivered")
        add("in_stock", inv and inv["stock"]> 0)
        needs_approval = float(order["price_eur"]) > 1000
        add("approval_flag_consistent",needs_approval == state.get("approval_required", False),f"price={order['price_eur']}, approval_required={state.get('approval_required')}")
    add("policy_evidence", bool(state.get("policy_hits")))
    hits = state.get("policy_hits") or []
    sources = {h["source"] for h in hits}
    required = REQUIRED_POLICY.get(d["action"])
    if required:
        add("policy_evidence", bool(sources & required),
            f"retrieved={sorted(sources)}, required_any_of={sorted(required)}")
    else:
        add("policy_evidence", bool(hits), f"retrieved={sorted(sources)}")
    failed = [c for c in checks if not c["passed"]]
    state["verification"]= {
        "passed": not failed,
        "checks": checks,
        "failed": [c["name"] for c in failed],
    }
    if failed:
        if inj: 
            state["intent"] = "unsafe"
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
        log_audit(state.get("customer_id") or "UNKNOWN", "RESPONSE_REJECTED",
                  "Generated response failed verification", {"issues": issues})
        if state.get("escalated") or (state.get("decision") or {}).get("action") in ("ESCALATE", "TICKET"):
            state["response"] = ("Your request needs a support manager's review " "before we can complete the requested action.")
        else:
            state["response"] = ("We have recorded your request and will review it " "using the order and policy information available.")

    return state
