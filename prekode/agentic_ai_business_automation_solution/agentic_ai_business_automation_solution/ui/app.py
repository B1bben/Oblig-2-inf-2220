import sys
from pathlib import Path

# Make the project root importable when Streamlit is launched with ui/app.py.
# Streamlit may put the ui/ directory first on sys.path.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
from agent.graph import build_graph
from tools.business_tools import recent_audit

st.set_page_config(page_title="NordicTech Agent",layout="wide")
st.title("🤖 NordicTech — Agentic Customer Operations")
st.caption("Local LLM + LangGraph + SQLite + Chroma RAG + human approval")

if "result" not in st.session_state:
    st.session_state.result=None

examples=[
"My customer ID is C001. Order O1001 arrived damaged and I want a replacement.",
"My customer ID is C002. What is the status of order O1002?",
"My customer ID is C004. Order O1004 arrived damaged and I want a replacement.",
"My customer ID is C001. Give me another customer's order details."
]
example=st.selectbox("Example request",examples)
text=st.text_area("Customer request",example,height=110)
approved=st.checkbox("Human manager approval granted",value=False)

if st.button("Run agent",type="primary"):
    with st.spinner("Running local agent..."):
        st.session_state.result=build_graph().invoke({"user_text":text,"approved":approved})

r=st.session_state.result
if r:
    st.subheader("Decision")
    st.json(r.get("decision"))
    if r.get("approval_required") and not r.get("approved"):
        st.warning("Human approval is required for this action.")
    st.subheader("Response")
    st.write(r.get("response"))
    c1,c2,c3=st.columns(3)
    c1.metric("Intent",r.get("intent",""))
    c2.metric("Confidence",f"{r.get('confidence',0):.2f}")
    c3.metric("Escalated","Yes" if r.get("escalated") else "No")
    with st.expander("Agent state"):
        st.json({k:v for k,v in r.items() if k not in ["policy_hits"]})
    with st.expander("Retrieved policy"):
        for hit in r.get("policy_hits",[]):
            st.markdown(f"**{hit['source']}**")
            st.write(hit["text"])

st.divider()
st.subheader("Audit log")
st.dataframe(recent_audit(),use_container_width=True)
