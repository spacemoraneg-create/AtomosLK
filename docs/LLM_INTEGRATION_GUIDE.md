# Atomos LLM Integration Guide

Welcome to the **Atomos LLM Integration Layer**. This guide provides everything required to connect downstream Large Language Models (Gemini, Claude, GPT, or local models) to the Atomos WSDC debate intelligence engine.

---

## 1. Architectural Overview

```
                          ┌───────────────────────────┐
                          │   Downstream User / UI   │
                          └─────────────┬─────────────┘
                                        │ (Chat / Prompt)
                                        ▼
                          ┌───────────────────────────┐
                          │  LLM Agent (Gemini/GPT)   │
                          │  with System Prompt &     │
                          │  Function Calling Tools   │
                          └─────────────┬─────────────┘
                                        │ Tool Call: name & arguments
                                        ▼
                          ┌───────────────────────────┐
                          │    atomos.tools           │
                          │    dispatch_tool()        │
                          └─────────────┬─────────────┘
                                        │ In-Process (<10ms)
                                        ▼
                          ┌───────────────────────────┐
                          │    atomos.query           │
                          │    AtomosQuery Facade     │
                          └──────┬──────┬──────┬──────┘
                                 │      │      │
            ┌────────────────────┼──────┼──────┼────────────────────┐
            ▼                    ▼      ▼      ▼                    ▼
     DebaterProfile        HeadToHead  Institutions  Motions   UnifiedSearch
            │                    │      │      │                    │
            └────────────────────┴──────┴──────┴────────────────────┘
                                        │
                                        ▼
                             data/atomos.db (SQLite)
```

---

## 2. Core LLM Function Catalog (`TOOL_SCHEMAS`)

Atomos exports 7 pre-defined, standardized function schemas in `atomos.tools.TOOL_SCHEMAS`:

| Tool Name | Key Parameters | When LLM Should Call It |
| :--- | :--- | :--- |
| **`search_entities`** | `query` (str), `entity_types` (optional list), `limit` (int) | **Always call this first** when a user mentions a debater name, school name/code, or motion topic to get exact IDs and canonical names. |
| **`get_debater_profile`** | `identifier` (name or ID), `compact` (bool) | Retrieve career stats, official Master Tab rank, national Critical Stats rank, overall substantive avg, tournament history, and outrounds. |
| **`get_head_to_head`** | `entity_a` (str), `entity_b` (str), `mode` ('auto'/'debater'/'team'/'school') | Direct clash history, win/loss splits, speaker margins, and records against mutual common opponents. |
| **`compare_institutions`** | `school_a` (str), `school_b` (str) | Side-by-side institutional comparison: IPI rank, squad depth, Elo, direct school clashes, and mutual rival records. |
| **`get_institutional_leaderboard`** | `min_debates` (int, default: 5) | Full national Institutional Power Index (IPI) rankings across Sri Lankan schools. |
| **`get_circuit_summary`** | *(none)* | High-level national vitals: total debaters, schools, tournaments, debates, valid speeches, and national side balance. |
| **`get_motion_analytics`** | `theme` (str), `query` (str), `extreme_only` (bool) | Side balance (Prop vs Opp), stage balance (Prelims vs Eliminations), thematic topic win rates, and extreme/balanced motions. |

---

## 3. Recommended LLM System Prompt

Inject the following system prompt into your LLM agent configuration:

```text
You are the Atomos Debate Intelligence Analyst, an elite AI assistant specializing in the Sri Lankan World Schools Debating Championship (WSDC) circuit.

You have access to the verified, forensically audited Atomos database containing every tournament, round, ballot, speech performance, and motion across the circuit.

CRITICAL OPERATING RULES:
1. ENTITY DISAMBIGUATION FIRST:
   - When a user asks about a person, school, or motion, NEVER guess their database ID or assume spelling.
   - Always call `search_entities(query=...)` first to retrieve the canonical name and Person ID.
   - For schools, users frequently use acronyms (e.g. 'RC' for Royal College, 'WC' for Wesley College, 'AC' for Ananda College, 'SJC' for St. Joseph's College, 'LC' for Ladies' College). The search tool handles these automatically.

2. ZERO HALLUCINATION POLICY:
   - All statistical metrics (substantive averages, speaker ranks, win percentages, IPI scores, head-to-head records) MUST come directly from tool outputs.
   - Never extrapolate or invent speaker scores or debate outcomes.
   - If a debater has fewer than 3 preliminary rounds in a tournament, explain that under WSDC rules they are ineligible for the Master Speaker Tab in that tournament.

3. CONCISE, PROFESSIONAL PRESENTATION:
   - Highlight key analytical takeaways: win rates, speaker margins, outround conversion, and direct clash history.
   - Use clean Markdown tables and bullet points for comparisons.
```

---

## 4. Python Integration Snippets

### A. Quick In-Process Python SDK (No HTTP, < 10ms Latency)

```python
import sys
sys.path.insert(0, "src")

from atomos.query import AtomosQuery

aq = AtomosQuery()

# 1. Search
results = aq.search("Royal")

# 2. Debater profile (compact mode saves ~70% tokens)
profile = aq.get_debater("Balishta Wijesinghe", compact=True)

# 3. Direct Head-to-Head
clash = aq.get_head_to_head("Royal College", "Ananda College", mode="school")

# 4. Motion Side Bias & Thematics
motions = aq.get_motion_analytics(theme="Economics & Development")

aq.close()
```

---

### B. Gemini 2.0 / 1.5 Function Calling Integration

```python
import google.generativeai as genai
from atomos.tools import TOOL_SCHEMAS, dispatch_tool

# Configure Gemini model
model = genai.GenerativeModel(
    model_name="gemini-2.0-flash",
    tools=[{"function_declarations": [s["function"] for s in TOOL_SCHEMAS]}],
    system_instruction="You are the Atomos Debate Intelligence Analyst..."
)

chat = model.start_chat(enable_automatic_function_calling=False)
response = chat.send_message("Who has the higher IPI ranking between Royal and Wesley?")

# Tool calling loop
while response.candidates[0].function_calls:
    for call in response.candidates[0].function_calls:
        tool_name = call.name
        tool_args = dict(call.args)
        
        # Execute tool via Atomos Dispatcher
        tool_result = dispatch_tool(tool_name, tool_args)
        
        # Send result back to model
        response = chat.send_message(
            genai.protos.Content(
                parts=[genai.protos.Part.from_function_response(
                    name=tool_name,
                    response={"result": tool_result}
                )]
            )
        )

print(response.text)
```

---

### C. OpenAI GPT-4o Function Calling Integration

```python
from openai import OpenAI
from atomos.tools import TOOL_SCHEMAS, dispatch_tool

client = OpenAI()

messages = [
    {"role": "system", "content": "You are the Atomos Debate Intelligence Analyst..."},
    {"role": "user", "content": "Compare Balishta Wijesinghe and Vidath Marasinghe"}
]

response = client.chat.completions.create(
    model="gpt-4o",
    messages=messages,
    tools=TOOL_SCHEMAS,
    tool_choice="auto"
)

# If model calls a tool
msg = response.choices[0].message
if msg.tool_calls:
    for tc in msg.tool_calls:
        fn_name = tc.function.name
        fn_args = json.loads(tc.function.arguments)
        
        result = dispatch_tool(fn_name, fn_args)
        
        messages.append(msg)
        messages.append({
            "role": "tool",
            "tool_call_id": tc.id,
            "name": fn_name,
            "content": json.dumps(result)
        })

    final_resp = client.chat.completions.create(model="gpt-4o", messages=messages)
    print(final_resp.choices[0].message.content)
```

---

## 5. Developer Console (`scripts/ask_atomos.py`)

You can test any tool or query directly from your shell without running an LLM:

```bash
# Print tool declarations for your prompt / API config:
python scripts/ask_atomos.py --tools

# Test entity search:
python scripts/ask_atomos.py search "Royal"

# Test debater profile:
python scripts/ask_atomos.py debater "Balishta"

# Test school rivalry:
python scripts/ask_atomos.py schools "RC" "WC"

# Test motions intelligence:
python scripts/ask_atomos.py motions --theme "Tech, AI & Science"

# Test IPI leaderboard:
python scripts/ask_atomos.py leaderboard --min-debates 10
```
