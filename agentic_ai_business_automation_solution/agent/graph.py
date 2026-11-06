import sqlite3
from langgraph.graph import StateGraph, END
from agent.state import AgentState
from agent.llm import classify_request, generate_response
from rag.retrieve import retrieve
from tools.business_tools import (
    get_customer,
    get_orders,
    get_order,
    check_inventory,
    create_ticket,
    create_replacement,
    log_audit,
    get_invoice,
    check_refund_eligibility,
    issue_refund,
    REFUND_AUTO_LIMIT_EUR,
)
from agent.reflection import reflect_on_decision
from agent.verification import (
    verify_decision,
    route_after_verify,
    verify_response,
    escalate_after_verify,
    route_after_response,
    fallback_response,
)
from agent.faults import fault_active


def identify_customer(state: AgentState):
    # Teaching shortcut: customer ID may be supplied as C001 etc.
    import re

    m = re.search(r"\bC\d{3}\b", state["user_text"], re.I)
    customer = get_customer(customer_id=m.group(0).upper()) if m else None
    state["customer"] = customer
    state["customer_id"] = customer["customer_id"] if customer else None
    return state


def classify(state):
    r = classify_request(state["user_text"])
    state["intent"] = r.get("intent")
    state["confidence"] = r.get("confidence", 0.0)
    return state


def load_customer_orders(state):
    if not state.get("customer_id"):
        state["error"] = "No verified customer identity was supplied."
        state["orders"] = []
        return state
    state["orders"] = get_orders(state["customer_id"])
    return state


def select_order(state):
    orders = state.get("orders", [])
    # Explicit order number wins.
    import re

    m = re.search(r"\bO\d{4}\b", state["user_text"], re.I)
    if m:
        state["selected_order"] = get_order(m.group(0).upper())
        return state
    # Otherwise use latest delivered order for the reference demo.
    delivered = [o for o in orders if o["status"] == "delivered"]
    state["selected_order"] = (
        delivered[0] if delivered else (orders[0] if orders else None)
    )
    return state


def load_invoice(state):
    order = state.get("selected_order")
    state["invoice"] = get_invoice(order["order_id"]) if order else None
    return state


def retrieve_policy(state):
    q = state["user_text"]
    state["policy_hits"] = [] if fault_active("rag_miss") else retrieve(q, 2)
    return state


def check_stock(state):
    order = state.get("selected_order")
    state["inventory"] = check_inventory(order["product_id"]) if order else None
    return state


def decide(state):
    order = state.get("selected_order")
    inv = state.get("inventory")
    intent = state.get("intent")

    decision = {"allowed": False, "reason": "", "action": "NONE"}
    if intent == "unsafe":
        decision = {
            "allowed": False,
            "reason": "Unsafe or privacy-sensitive request.",
            "action": "ESCALATE",
        }
    elif not state.get("customer"):
        decision = {
            "allowed": False,
            "reason": "Customer identity could not be verified.",
            "action": "TICKET",
        }
    elif not order:
        decision = {
            "allowed": False,
            "reason": "No matching order was found.",
            "action": "TICKET",
        }
    elif intent == "replacement":
        if order["status"] != "delivered":
            decision = {
                "allowed": False,
                "reason": "Order is not delivered; replacement requires review.",
                "action": "ESCALATE",
            }
        elif not inv or inv["stock"] <= 0:
            decision = {
                "allowed": False,
                "reason": "Replacement product is out of stock.",
                "action": "TICKET",
            }
        elif float(order["price_eur"]) > 1000:
            decision = {
                "allowed": True,
                "reason": "Replacement appears eligible but exceeds EUR 1000 approval threshold.",
                "action": "REPLACEMENT",
                "approval_required": True,
            }
        else:
            decision = {
                "allowed": True,
                "reason": "Delivered order, replacement request, and stock are consistent.",
                "action": "REPLACEMENT",
                "approval_required": False,
            }
    elif intent == "refund":
        check = check_refund_eligibility(state.get("invoice"), order)
        if not check["eligible"]:
            decision = {
                "allowed": False,
                "reason": check["reason"],
                "action": check["route"],
            }
        else:
            needs = check["amount_eur"] > REFUND_AUTO_LIMIT_EUR
            decision = {
                "allowed": True,
                "reason": check["reason"]
                + (
                    f" Amount exceeds EUR {REFUND_AUTO_LIMIT_EUR} auto-approval limit."
                    if needs
                    else ""
                ),
                "action": "REFUND",
                "approval_required": needs,
            }
    elif intent == "status":
        decision = {
            "allowed": True,
            "reason": "Order status can be reported.",
            "action": "RESPOND",
        }
    else:
        decision = {
            "allowed": False,
            "reason": "General request requires support handling.",
            "action": "TICKET",
        }

    state["decision"] = decision
    state["approval_required"] = bool(decision.get("approval_required", False))
    return state


def human_gate(state):
    # CLI/UI supplies approval through the initial state.
    if state.get("approval_required"):
        if state.get("approved") is True:
            state["escalated"] = False
        else:
            state["escalated"] = True
    return state


def execute(state):
    d = state["decision"]
    order = state.get("selected_order")
    if d["action"] == "REFUND" and not state.get("escalated"):
        inv = state["invoice"]
        for _ in range(2):  # retry once
            try:
                state["refund"] = issue_refund(
                    inv["invoice_id"],
                    inv["amount_eur"],
                    "HUMAN_APPROVED" if state.get("approval_required") else "SYSTEM",
                )
                break
            except sqlite3.OperationalError as e:  # transient: retry
                state["error"] = str(e)
            except Exception as e:  # deterministic: do not retry
                state["error"] = str(e)
                break
        if not state.get("refund"):  # fallback: escalate to a ticket
            state["escalated"] = True
            d = state["decision"] = {
                "allowed": False,
                "action": "ESCALATE",
                "reason": f"Refund could not be processed: {state['error']}",
            }
    if d["action"] == "REPLACEMENT" and not state.get("escalated"):
        state["replacement"] = create_replacement(
            order["order_id"],
            state["customer_id"],
            order["product_id"],
            "HUMAN_APPROVED" if state.get("approval_required") else "SYSTEM",
        )
    elif d["action"] in ("TICKET", "ESCALATE") or state.get("escalated"):
        state["ticket"] = create_ticket(
            state.get("customer_id") or "UNKNOWN",
            order["order_id"] if order else "",
            "support",
            state["decision"]["reason"],
        )
    log_audit(
        state.get("customer_id") or "UNKNOWN",
        d["action"],
        d["reason"],
        {
            "order": order,
            "replacement": state.get("replacement"),
            "ticket": state.get("ticket"),
            "verification": state.get("verification"),
            "blocked_order_id": state.get("blocked_order_id"),
            "reflection_log": state.get("reflection_log"),
            "invoice": state.get("invoice"),
            "refund": state.get("refund"),
        },
    )
    return state


def respond(state):
    ctx = {
        "customer": state.get("customer"),
        "order": state.get("selected_order"),
        "decision": state.get("decision"),
        "approved": state.get("approved", False),
        "escalated": state.get("escalated", False),
        "replacement": state.get("replacement"),
        "ticket": state.get("ticket"),
        "policy": state.get("policy_hits", []),
    }
    attempts = state.get("response_attempts", 0)
    feedback = state.get("response_issues") if attempts else None
    if not state.get("customer_id"):
        state["response"] = (
            "We could not verify your identity. Please include your customer ID"
        )
        state["response_attempts"] = state.get("response_attempts", 0) + 1
        return state
    if feedback:
        state.setdefault("reflection_log", []).append(
            {"stage": "response", "attempt": attempts + 1, "issues": feedback}
        )
    state["response"] = generate_response(ctx, feedback=feedback)
    state["response_attempts"] = attempts + 1
    return state


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("identify_customer", identify_customer)
    g.add_node("classify", classify)
    g.add_node("load_customer_orders", load_customer_orders)
    g.add_node("select_order", select_order)
    g.add_node("retrieve_policy", retrieve_policy)
    g.add_node("check_stock", check_stock)
    g.add_node("decide", decide)
    g.add_node("verify_decision", verify_decision)
    g.add_node("human_gate", human_gate)
    g.add_node("execute", execute)
    g.add_node("respond", respond)
    g.add_node("load_invoice", load_invoice)
    g.add_node("verify_response", verify_response)
    g.add_node("reflect", reflect_on_decision)
    g.add_node("escalate_after_verify", escalate_after_verify)
    g.add_node("fallback_response", fallback_response)

    g.set_entry_point("identify_customer")
    g.add_edge("identify_customer", "classify")
    g.add_edge("classify", "load_customer_orders")
    g.add_edge("load_customer_orders", "select_order")
    g.add_edge("select_order", "load_invoice")
    g.add_edge("load_invoice", "retrieve_policy")
    g.add_edge("retrieve_policy", "check_stock")
    g.add_edge("check_stock", "decide")
    g.add_edge("decide", "verify_decision")
    g.add_conditional_edges(
        "verify_decision",
        route_after_verify,
        {"ok": "human_gate", "reflect": "reflect", "escalate": "escalate_after_verify"},
    )
    g.add_edge("reflect", "decide")
    g.add_edge("escalate_after_verify", "execute")
    g.add_edge("human_gate", "execute")
    g.add_edge("execute", "respond")
    g.add_edge("respond", "verify_response")
    g.add_conditional_edges(
        "verify_response",
        route_after_response,
        {"ok": END, "retry": "respond", "fallback": "fallback_response"},
    )
    g.add_edge("fallback_response", END)
    return g.compile()
