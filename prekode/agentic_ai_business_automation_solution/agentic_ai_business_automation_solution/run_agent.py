from agent.graph import build_graph

def run(text, approved=False):
    app=build_graph()
    result=app.invoke({"user_text":text,"approved":approved})
    print("\n=== AGENT RESULT ===")
    for k in ["intent","confidence","customer","selected_order","policy_hits","inventory","decision","approval_required","escalated","ticket","replacement"]:
        print(f"\n{k}: {result.get(k)}")
    print("\nresponse:")
    print(result.get("response"))
    return result

if __name__=="__main__":
    print("Example customer identity must be explicit for this teaching demo.")
    print("Try: My customer ID is C001. Order O1001 arrived damaged and I want a replacement.")
    text=input("\nRequest: ")
    approved=input("Approve sensitive action if requested? [y/N]: ").strip().lower()=="y"
    run(text,approved)
