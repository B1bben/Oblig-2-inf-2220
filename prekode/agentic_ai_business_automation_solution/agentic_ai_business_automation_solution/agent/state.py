from typing import TypedDict, Any, Optional

class AgentState(TypedDict, total=False):
    user_text: str
    customer_id: Optional[str]
    customer: Any
    intent: str
    confidence: float
    orders: Any
    selected_order: Any
    policy_hits: Any
    inventory: Any
    decision: Any
    approval_required: bool
    approved: bool
    verification: Any
    response_verified: bool
    response_issues: Any
    escalated: bool
    ticket: Any
    replacement: Any
    response: str
    audit: Any
    injection_flags: Any
    error: Optional[str]
