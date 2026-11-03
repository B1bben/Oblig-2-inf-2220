# Agentic AI for Business Automation — Complete Local Project

A teaching/reference implementation for a 6-hour course project.

## Business case

**NordicTech** is a fictional technology retailer. The agent handles customer support requests such as:

> "My laptop arrived damaged. I want a replacement."

The agent can:
1. Identify a customer.
2. Retrieve an order.
3. Retrieve product details.
4. Search company policies with local RAG.
5. Check inventory.
6. Decide whether a replacement is allowed.
7. Escalate sensitive cases for human approval.
8. Create a support ticket.
9. Create a replacement order in a sandbox database.
10. Generate a response.
11. Write an audit log.

## Architecture

User
  ↓
Local LLM (Ollama / Qwen3)
  ↓
LangGraph state machine
  ├── customer lookup
  ├── order lookup
  ├── policy RAG (Chroma + Sentence Transformers)
  ├── inventory lookup
  ├── decision / guardrails
  ├── human approval
  ├── sandbox action
  └── audit logging
  ↓
Streamlit UI

## Requirements

- Python 3.10+
- Ollama
- A local Ollama model, e.g. Qwen3
- No paid API is required.
- The project uses synthetic data only.

## Quick start

### 1. Create environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows:

```powershell
.venv\Scripts\activate
```

### 2. Install and run Ollama

Install Ollama from its official installer, then:

```bash
ollama pull qwen3:8b
ollama serve
```

If your computer is weak, use a smaller locally available Qwen3 model.

### 3. Initialize the database

```bash
python scripts_init.py
```

### 4. Build the local RAG index

```bash
python rag/ingest.py
```

### 5. Run the CLI demo

```bash
python run_agent.py
```

Try:

```text
My laptop arrived damaged. I want a replacement.
```

### 6. Run the UI

```bash
streamlit run ui/app.py
```

## Important teaching design

The LLM is **not** allowed to directly execute arbitrary Python or SQL.

Business actions are exposed as explicit tools. Sensitive actions go through an approval gate. The database uses a sandbox SQLite file. Every important decision/action is logged.

## Evaluation

Run:

```bash
python evaluation/evaluate.py
```

The included 50 cases cover:
- straightforward requests
- ambiguous requests
- policy edge cases
- missing data
- adversarial/unsafe requests

The evaluator reports task success, decision accuracy, escalation rate, and failure examples.

## Suggested student extensions

- Add email tools using a local mock email service.
- Add invoice processing.
- Add CRM updates.
- Add a planner node.
- Add human approval through the UI.
- Add role-based permissions.
- Add retrieval evaluation.
- Add latency and token measurements.
- Compare deterministic vs LLM-assisted routing.
