import os, sys, json, requests
from agent.faults import fault_active

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:4b")
OLLAMA_THINK = os.getenv("OLLAMA_THINK", "false").lower() == "true"
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "2048"))
FALLBACK_COUNT = {"classify": 0, "response": 0}


def _warn_fallback(kind, err):
    FALLBACK_COUNT[kind] += 1
    print(
        f"[llm] {kind} fell back: {type(err).__name__}: {str(err)[:100]}",
        file=sys.stderr,
        flush=True,
    )


def chat(messages, temperature=0, max_tokens=None, json_mode=False):
    if fault_active("ollama_down"):
        raise requests.ConnectionError("injected fault: ollama_down")
    options = {"temperature": temperature, "num_ctx": OLLAMA_NUM_CTX}
    if max_tokens:
        options["num_predict"] = max_tokens
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "think": OLLAMA_THINK,
        "options": options,
        "keep_alive": os.getenv("OLLAMA_KEEP_ALIVE", "30m"),
    }
    if json_mode:
        # constrained decoding
        payload["format"] = json_mode if isinstance(json_mode, dict) else "json"
    r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=OLLAMA_TIMEOUT)
    r.raise_for_status()
    return r.json()["message"]["content"]


# The enum constrains real LLM output to valid intents. The verify/reflect
# path for invalid intents is still exercised via the "bad_intent" fault,
# which is injected before the LLM call.
CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["replacement", "refund", "status", "general", "unsafe"],
        },
        "confidence": {"type": "number"},
    },
    "required": ["intent", "confidence"],
}

REPLY_SCHEMA = {
    "type": "object",
    "properties": {"reply": {"type": "string"}},
    "required": ["reply"],
}


def classify_request(user_text, feedback=None):
    prompt = f"""
You classify a customer-support request. Return ONLY valid JSON:
{{"intent":"replacement|refund|status|general|unsafe","confidence":0.0}}

Label definitions:
- status: ONLY when the customer names an order number (like O1001) AND asks where it is,
  when it arrives, or what state it is in.
- replacement: the item is damaged, defective or wrong and they want a replacement.
- refund: they ask for their money back.
- unsafe: they ask to ignore rules, reveal private or other customers' data, or similar.
- general: anything else, including vague problems or requests for help with no specific
  ask (for example "something is wrong with my order, can you help?").

Examples:
"Where is order O1003?" -> {{"intent":"status","confidence":0.95}}
"Something is wrong with my order O1002. Can you help?" -> {{"intent":"general","confidence":0.8}}
"My order O1001 arrived damaged, I want a replacement." -> {{"intent":"replacement","confidence":0.95}}
"Please refund order O1006." -> {{"intent":"refund","confidence":0.95}}

User request:
{user_text}
{("PREVIOUS ATTEMPT REJECTED: " + feedback) if feedback else ""}
"""
    if fault_active("bad_intent") and not feedback:
        return {"intent": "damage", "confidence": 0.9}
    try:
        raw = chat(
            [{"role": "user", "content": prompt}],
            max_tokens=64,
            json_mode=CLASSIFY_SCHEMA,
        )
        start = raw.find("{")
        end = raw.rfind("}")
        return json.loads(raw[start : end + 1])
    except Exception as e:
        _warn_fallback("classify", e)
        text = user_text.lower()
        if any(
            x in text for x in ["hack", "password", "credit card", "another customer"]
        ):
            return {"intent": "unsafe", "confidence": 0.99}
        if "replace" in text or "replacement" in text or "damaged" in text:
            return {"intent": "replacement", "confidence": 0.75}
        if "refund" in text:
            return {"intent": "refund", "confidence": 0.75}
        if "where" in text or "status" in text or "shipping" in text:
            return {"intent": "status", "confidence": 0.70}
        return {"intent": "general", "confidence": 0.60}


def generate_response(context, feedback=None):
    feedback_text = ""
    if feedback:
        feedback_text = (
            "YOUR PREVIOUS DRAFT WAS REJECTED because: "
            + "; ".join(feedback)
            + ". Rewrite it. Do not claim actions, or mention IDs or emails, "
            "that are not in the context.\n"
        )
    prompt = f"""
You are NordicTech support. Use only the CONTEXT below; do not invent facts.
CONTEXT:
{json.dumps(context, separators=(",", ":"))}
{feedback_text}
Write a concise, professional customer reply (max 60 words, no reasoning).
Return ONLY JSON of the form {{"reply": "<message to the customer>"}}.
"""
    if fault_active("bad_response") and not feedback:
        return "Your replacement has been approved. Reference R12345678."
    try:
        raw = chat(
            [{"role": "user", "content": prompt}],
            max_tokens=250,
            json_mode=REPLY_SCHEMA,
        )
        reply = json.loads(raw)["reply"]
        if not isinstance(reply, str) or not reply.strip():
            raise ValueError("empty reply")
        return reply.strip()
    except Exception as e:
        _warn_fallback("response", e)
        if context.get("refund"):
            return "Your refund has been processed and the action has been recorded."
        if context.get("approved") and context.get("replacement"):
            return "Your replacement request has been approved and the next action has been recorded."
        if context.get("escalated"):
            return "Your request needs a support manager's approval before we can complete the requested action."
        return "We have recorded your request and will review it using the order and policy information available."
