import json, sys, os, time
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))

from agent.graph import build_graph
import scripts_init

scripts_init.main()  # fresh sandbox DB every run
files = sys.argv[1:] or ["test_cases.json", "test_cases_V2.json"]
cases = [c for f in files for c in json.loads((ROOT / "evaluation" / f).read_text())]
app = build_graph()
results = []
for i, case in enumerate(cases, 1):
    os.environ["inject_fault"] = case.get("inject_fault", "")
    for k, v in case.get("env", {}).items():
        os.environ[k] = v
    t0 = time.perf_counter()
    try:
        r = app.invoke(
            {"user_text": case["query"], "approved": case.get("approved", False)}
        )
        action = (r.get("decision") or {}).get("action")
        intent = r.get("intent")
        exp = case.get("expected_outcome")
        outcome_ok = (
            (exp != "replacement_created" or bool(r.get("replacement")))
            and (exp != "refund_created" or bool(r.get("refund")))
            and (exp != "no_refund" or not r.get("refund"))
        )
        results.append(
            {
                "id": case["id"],
                "category": case.get("category", ""),
                "inject_fault": case.get("inject_fault", ""),
                "intent_ok": intent == case["expected_intent"],
                "action_ok": action == case["expected_action"] and outcome_ok,
                "intent": intent,
                "expected_intent": case["expected_intent"],
                "action": action,
                "expected_action": case["expected_action"],
                "should_refuse": case.get("should_refuse", False),
                "escalated": bool(r.get("escalated"))
                or action in ("ESCALATE", "TICKET"),
                "decision_attempts": r.get("decision_attempts", 0),
                "response_attempts": r.get("response_attempts", 0),
                "fallback": not r.get("response_verified", True),
                "latency_s": time.perf_counter() - t0,
                "query": case["query"],
            }
        )
    except Exception as e:
        results.append(
            {
                "id": case["id"],
                "intent_ok": False,
                "action_ok": False,
                "error": str(e),
                "query": case["query"],
            }
        )
    finally:
        os.environ["inject_fault"] = ""
        for k in case.get("env", {}):
            os.environ.pop(k, None)
    x = results[-1]
    status = "PASS" if x.get("intent_ok") and x.get("action_ok") else "FAIL"
    lat = f"{x['latency_s']:.1f}s" if "latency_s" in x else "error"
    print(f"[{i}/{len(cases)}]{case['id']}{status}({lat})", flush=True)

intent_acc = sum(x["intent_ok"] for x in results) / len(results)
action_acc = sum(x["action_ok"] for x in results) / len(results)

print(f"Cases: {len(results)}")
print(f"Intent accuracy: {intent_acc:.3f}")
print(f"Decision/action accuracy: {action_acc:.3f}")
ok = [x for x in results if "latency_s" in x]
faulted = [x for x in ok if x["inject_fault"]]
print(f"Avg latency: {sum(x['latency_s'] for x in ok) / len(ok):.2f}s")
print(f"Cases with decision retry: {sum(x['decision_attempts'] > 0 for x in ok)}")
print(f"Cases with response retry: {sum(x['response_attempts'] > 1 for x in ok)}")
print(f"Response fallbacks: {sum(x['fallback'] for x in ok)}")
if faulted:
    print(
        f"Failure-recovery rate: {sum(x['action_ok'] for x in faulted) / len(faulted):.3f}"
    )
refuse = [x for x in ok if x["should_refuse"]]
if refuse:
    print(
        f"Safety success rate: {sum(x['action_ok'] for x in refuse) / len(refuse):.3f}"
    )
print(f"Escalation rate: {sum(x['escalated'] for x in ok) / len(ok):.3f}")
print("\nFailures:")
for x in results:
    if not (x.get("intent_ok") and x.get("action_ok")):
        print(x)
