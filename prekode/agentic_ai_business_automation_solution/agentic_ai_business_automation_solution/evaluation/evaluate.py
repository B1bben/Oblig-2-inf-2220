import json, sys
from pathlib import Path

ROOT=Path(__file__).parents[1]
sys.path.insert(0,str(ROOT))

from agent.graph import build_graph

cases=json.loads((ROOT/"evaluation/test_cases.json").read_text())
app=build_graph()

results=[]
for case in cases:
    try:
        r=app.invoke({"user_text":case["query"],"approved":False})
        action=(r.get("decision") or {}).get("action")
        intent=r.get("intent")
        ok_intent=intent==case["expected_intent"]
        ok_action=action==case["expected_action"]
        results.append({
            "id":case["id"],"intent_ok":ok_intent,"action_ok":ok_action,
            "intent":intent,"expected_intent":case["expected_intent"],
            "action":action,"expected_action":case["expected_action"],
            "query":case["query"]
        })
    except Exception as e:
        results.append({"id":case["id"],"intent_ok":False,"action_ok":False,"error":str(e),"query":case["query"]})

intent_acc=sum(x["intent_ok"] for x in results)/len(results)
action_acc=sum(x["action_ok"] for x in results)/len(results)

print(f"Cases: {len(results)}")
print(f"Intent accuracy: {intent_acc:.3f}")
print(f"Decision/action accuracy: {action_acc:.3f}")
print("\nFailures:")
for x in results:
    if not (x.get("intent_ok") and x.get("action_ok")):
        print(x)
