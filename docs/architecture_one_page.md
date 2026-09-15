# NeoBank ARIA — One-page architecture

A consolidated view of the [final project paper](NeoBank_ARIA_Final_Project_Paper.docx), covering application execution, defenses, data access, and evaluation. See the [architecture atlas](architecture.md) for the six detailed views.

```mermaid
flowchart LR
    UI["Streamlit interface<br/>Demo identity · mode · chat history"]

    subgraph APP["LOCAL PYTHON APPLICATION"]
        MODE{"Mode"}
        BASE["Unguarded<br/>Baseline prompt"]
        GUARD["Guarded<br/>Input screening<br/>Four-turn risk window"]
        AGENT["Shared agent runtime<br/>Plan → validate batch → execute<br/>Maximum 8 tool calls<br/>Final response without tools"]
        SCAN["Output screening"]
        REPLY["Customer response<br/>or safe refusal"]

        MODE -->|Unguarded| BASE
        MODE -->|Guarded| GUARD
        BASE --> AGENT
        GUARD -->|Allow| AGENT
        GUARD -->|Block or review| REPLY
        AGENT -->|Unguarded| REPLY
        AGENT -->|Guarded| SCAN
        SCAN --> REPLY
    end

    UI --> MODE

    subgraph DATA["LOCAL TOOLS AND DATA"]
        TOOLS["Python tool boundary<br/>Guarded: session account only<br/>Public policy allowlist + redaction<br/>Unguarded: broad account/topic access"]
        DB[("SQLite<br/>4 fictional customers<br/>15 transactions")]
        KB["Policy dictionary<br/>5 public topics · 1 internal"]
        TOOLS <--> DB
        TOOLS <--> KB
    end

    AGENT <-->|Tool calls / results| TOOLS

    API["EXTERNAL MODEL API<br/>OpenAI through LangChain<br/>Planning · response · classifier · judge"]
    AGENT <-->|Prompts / model output| API
    GUARD -. Optional classifier .-> API

    subgraph EVAL["EVALUATION AND EVIDENCE"]
        SUITE["YAML test suite + runner<br/>43 attacks + 10 benign cases<br/>Both modes"]
        SCORE["Assess every turn<br/>Security · utility<br/>Execution · judge availability"]
        RECORD[("Schema 2 JSONL<br/>All-turn outcomes and traces<br/>Configuration + fingerprints")]
        REPORT["Offline findings reports<br/>HTML + Markdown"]
        SCORE -->|Aggregate conversation| RECORD
        RECORD --> REPORT
    end

    SUITE -->|Execute cases| MODE
    REPLY -. Responses and guard traces .-> SCORE
    AGENT -. Execution and tool-scope traces .-> SCORE
    SCORE -. Optional security judge .-> API
```

**Boundary:** Guarded tools enforce account access in application code. Identity selection is a demo; tools are read-only, and “review” returns a static message. A direct model answer skips tool execution. Evaluation observes every turn and does not control the customer response.

Source references: [technical reference](technical_reference.md), [validation record](validation.md), and [documentation index](README.md).
