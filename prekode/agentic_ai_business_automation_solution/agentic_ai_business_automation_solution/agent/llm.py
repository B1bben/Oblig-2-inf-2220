import os, json, requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")


def chat(messages, temperature=0):
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }
    r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=120)
    r.raise_for_status()
    return r.json()["message"]["content"]


def classify_request(user_text, feedback=None):
    prompt = f"""
You classify a customer-support request. Return ONLY valid JSON:
{{"intent":"replacement|refund|status|general|unsafe","confidence":0.0}}
User request:
{user_text}
19 {("PREVIOUS ATTEMPT REJECTED: " + feedback) if feedback else ""}
"""
    try:
        raw = chat([{"role": "user", "content": prompt}])
        start = raw.find("{")
        end = raw.rfind("}")
        return json.loads(raw[start : end + 1])
    except Exception:
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
            "that are not in the context."
        )
    prompt = f"""
 You are NordicTech support. Write a concise, professional customer response.
 Do not invent facts. Use only the supplied context.
 CONTEXT:
 {json.dumps(context, indent=2)}
 {feedback_text}
 """
    try:
        return chat([{"role": "user", "content": prompt}])
    except Exception:
        if context.get("approved"):
            return "Your replacement request has been approved and the next action has been recorded."
        if context.get("escalated"):
            return "Your request needs a support manager's approval before we can complete the requested action."
        return "We have recorded your request and will review it using the order and policy information available."
