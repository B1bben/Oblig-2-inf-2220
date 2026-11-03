import re
import unicodedata

PATTERNS = {
    "override_instructions": r"\b(ignore|disregard|forget|bypass|override)\b.{0,40}\b(instructions?|polic(y|ies)|rules?|guidelines?|prompt)\b",

    "other_customer_data": r"\b(other|another|private|all)\s+(customers?|users?|clients?)('s)?\b",

    "data_exfiltration": r"\b(reveal|dump|export|leak)\b.{0,40}\b(records?|data|database|passwords?)\b",

    "role_hijack": r"\b(you are now|act as| pretend to be| developer mode|jailbreak|system prompt)\b",

    "fake_authorization": r"\b(manager|admin|supervisor)\b.{0,30}\b(approved|authori[sz]ed)\b|\bi am (an? )?(admin|manager|employee)\b",

  }
def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"\s+", " ", text.lower()).strip()

def scan(text: str) -> list[str]:
    t = normalize(text)
    hits = [ name for name, pattern in PATTERNS.items() if re.search(pattern, t)]
    if len({m for m in re.findall(r"\bc\d{3}\b", t)}) > 1:
        hits.append("multiple_customer_ids")
    return hits
