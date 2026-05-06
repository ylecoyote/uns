Below is a **single-page, shareable system diagram** you can drop into a doc, Notion, or README. I’ll give you:

1. A **Mermaid diagram** (copy/paste)
2. A **plain-English legend** you can include under it
3. A **one-sentence framing blurb** to send with it

No fluff, no marketing gloss.

---

## UNS — One-Pager System Map (Diagram)

### Mermaid (source of truth)

```mermaid
flowchart LR
    subgraph Agent_System
        A[Autonomous Agent]
        G[Agent Governor]
    end

    A -->|emits intent + context| N[Unified Notification Service]

    subgraph UNS
        R[Router<br/>(YAML Policy)]
        S[Notification State Machine]
        D[(Notification Store)]
        Q[(DLQ)]
    end

    N --> R
    R --> S
    S --> D

    %% Delivery
    R -->|route| C1[Slack / Email]
    R -->|escalate| C2[PagerDuty]
    R -->|fallback| Q

    %% Human loop
    C1 --> H[Human]
    C2 --> H
    H -->|ACK / DISMISS| API[/ACK API/]

    API --> S

    %% Feedback
    S -->|audit + signal| G
```

---

## Diagram Legend (human-readable)

### Autonomous Agent

* Makes decisions
* Emits **notifications**, not alerts
* Never waits for humans

### Unified Notification Service (UNS)

The **control plane** — not execution, not learning.

**Router**

* Deterministic, YAML-driven
* Chooses *how* and *where* to notify
* Knows autonomy mode (PREVIEW / SHADOW / LIVE)

**Notification State Machine**

* PENDING → DELIVERED → ACKED / DISMISSED / TIMED_OUT
* ACKs are state transitions, not UI events

**Notification Store**

* Immutable audit trail
* Who knew what, when, and how it resolved

**DLQ**

* Visible failure mode
* GUARANTEED notifications never fail silently

### Humans

* Receive notifications via normal tools
* Acknowledge explicitly
* Never block execution

### Agent Governor

* Observes ACKs as **governance signals**
* May influence *future* autonomy
* Never rewrites history

---

## One-Sentence Framing (send this with the diagram)

> “UNS is a control-plane system where notifications and acknowledgments become auditable governance signals for autonomous agents — without ever blocking execution.”

---
