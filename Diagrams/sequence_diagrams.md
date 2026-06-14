# Sequence Diagrams for Ticketing System

This document contains detailed **Mermaid sequence diagrams** representing the step-by-step logic, function calls, and interactions of all system processes.

---

## 👥 1. Ticket Creation & AI Triage Process (Synchronous)

This diagram shows the flow when a customer submits a new ticket. It illustrates how the initial message is created, which immediately triggers the Django post-save signal to run the AI Triage classification.

```mermaid
sequenceDiagram
    autonumber
    actor Customer as 👤 Customer
    participant Views as 🖥️ Django Views<br/>(create_ticket_view)
    participant DB as 🗄️ SQLite Database
    participant Signals as ⚡ Django Signals<br/>(trigger_ai_triage)
    participant Triage as 🤖 AI Triage Module<br/>(analyze_and_update_ticket)
    participant NVIDIA as ☁️ NVIDIA AI Endpoint<br/>(moonshotai/kimi-k2.6)

    Customer->>Views: Submits ticket form (Title + Message)
    activate Views
    Views->>DB: Saves Ticket instance (Status: Open, Priority: Low)
    Views->>DB: Creates TicketMessage instance (initial description)
    activate DB
    DB->>Signals: Triggers post_save signal on TicketMessage
    activate Signals
    deactivate DB
    
    Signals->>Signals: Verifies it is the 1st ticket message
    Signals->>Triage: Invokes analyze_and_update_ticket(ticket_id, message_text)
    activate Triage
    
    Triage->>DB: Fetches Ticket title and details
    Triage->>NVIDIA: Sends payload with system prompt & message
    activate NVIDIA
    NVIDIA-->>Triage: Returns classification JSON: {"priority": "...", "explanation": "..."}
    deactivate NVIDIA
    
    Triage->>Triage: Validates JSON format & extracts values
    alt Refusal message detected
        Triage->>Triage: Overrides explanation with operational fallback
    end
    
    Triage->>DB: Saves Ticket priority & triage_explanation
    Triage-->>Signals: Returns success
    deactivate Triage
    Signals-->>Views: Signal processing completes
    deactivate Signals
    
    Note over Views: Proceeds to run RAG Auto-Response Pipeline...
    deactivate Views
```

---

## 🔍 2. RAG Pipeline & Auto-Response Process (Synchronous)

Directly following AI Triage, the view initiates the RAG pipeline. This diagram maps how historical candidate tickets are loaded, embedded, scored via the custom Keras Reranker, and used to auto-resolve a ticket if relevance meets the threshold.

```mermaid
sequenceDiagram
    autonumber
    participant Views as 🖥️ Django Views<br/>(create_ticket_view)
    participant RAG as 🔍 RAG Pipeline<br/>(process_new_ticket_for_rag)
    participant DB as 🗄️ SQLite Database
    participant Embed as 🧠 SentenceTransformers<br/>(all-MiniLM-L6-v2)
    participant Reranker as ⚙️ Keras Reranker Model
    participant NVIDIA as ☁️ NVIDIA AI Endpoint<br/>(z-ai/glm-5.1)

    activate Views
    Views->>RAG: Invokes process_new_ticket_for_rag(ticket)
    activate RAG
    
    RAG->>DB: Queries up to 50 recent closed tickets in category
    activate DB
    DB-->>RAG: Returns list of candidate tickets
    deactivate DB
    
    RAG->>Embed: Encodes new ticket: title + description
    activate Embed
    Embed-->>RAG: Returns 384d vector (query_emb)
    RAG->>Embed: Encodes all candidates: titles + descriptions
    Embed-->>RAG: Returns list of 384d vectors (doc_embs)
    deactivate Embed
    
    RAG->>RAG: Computes Cosine Similarity scores
    
    alt Custom reranker weights file exists
        RAG->>Reranker: Invokes model.predict([query_emb, doc_emb])
        activate Reranker
        Reranker-->>RAG: Returns neural network scores
        deactivate Reranker
        RAG->>RAG: Blends score = max(cosine, reranker)
    end
    
    RAG->>RAG: Checks and applies Title Exact Match boost (0.95)
    RAG->>DB: Bulk creates TicketRetrievalCandidate records
    
    alt Highest score >= RAG_RERANK_THRESHOLD (0.85)
        RAG->>RAG: Retrieves last resolution message from matching ticket
        RAG->>NVIDIA: Invokes ChatNVIDIA with system prompt, resolution, & new text
        activate NVIDIA
        NVIDIA-->>RAG: Returns rewritten & anonymized response text
        deactivate NVIDIA
        
        RAG->>DB: Creates TicketMessage from "ai_agent"
        RAG->>DB: Sets Ticket status to "Closed"
        RAG->>DB: Appends training pair to RerankerTrainingData (label: 1.0)
    else Highest score < 0.85
        Note over RAG: Leaves ticket status open for humans
    end
    
    RAG-->>Views: Pipeline completes
    deactivate RAG
    Views-->>Customer: Redirects customer to ticket detail view
    deactivate Views
```

---

## 👑 3. Supervisor Dispatch System (Synchronous)

This diagram shows how a supervisor views, updates, and assigns tickets to human agents, establishing the queue entry structure.

```mermaid
sequenceDiagram
    autonumber
    actor Supervisor as 👑 Supervisor
    participant Views as 🖥️ Django Views<br/>(dispatch_dashboard_view)
    participant DB as 🗄️ SQLite Database

    Supervisor->>Views: Submits dispatch assignment (ticket_id, agent_id)
    activate Views
    
    Views->>DB: Fetches ticket by ID
    Views->>DB: Fetches target agent profile by ID
    Views->>DB: Counts existing queue size for target agent
    
    Views->>Views: Computes queue rank = existing_count + 1
    
    Views->>DB: Creates or updates RerankedQueue entry (relevance=1.0, rank, agent)
    Views->>DB: Updates ticket status to "In Progress"
    
    Views-->>Supervisor: Redirects back to Dispatch Console
    deactivate Views
```

---

## 💬 4. Agent/Customer Message Interactions & Status Management (Synchronous)

This diagram highlights the smart status management flow when messages are exchanged between agents and customers inside a ticket conversation thread.

    ```mermaid
    sequenceDiagram
        autonumber
        actor User as 👤 Customer / Agent
        participant Views as 🖥️ Django Views<br/>(ticket_detail_view)
        participant DB as 🗄️ SQLite Database

        User->>Views: Posts new reply message (POST request)
        activate Views
        Views->>DB: Verifies user permissions to view thread
        
        Views->>DB: Creates TicketMessage record
        
        alt Sender is Customer AND ticket status is Closed
            Views->>DB: Sets ticket status to "Open"
            Note over Views, DB: Re-opens ticket for agent attention
        else Sender is Agent/Supervisor AND ticket status is Open
            Views->>DB: Sets ticket status to "In Progress"
            Note over Views, DB: Moves ticket into agent workspace loop
        end
        
        Views-->>User: Redirects back to refresh details thread
        deactivate Views
```

---

## ⚙️ 5. Reranker Retraining Task (Asynchronous Celery)

This diagram maps the offline neural network training sequence triggered by background workers, showing how training data batches are compiled and fitted.

```mermaid
sequenceDiagram
    autonumber
    participant Celery as ⏰ Celery Worker
    participant Task as ⚙️ Celery Task<br/>(train_tf_reranker_task)
    participant DB as 🗄️ SQLite Database
    participant Embed as 🧠 SentenceTransformers<br/>(all-MiniLM-L6-v2)
    participant Model as 🤖 Keras Reranker model
    participant Storage as 💾 Disk Storage

    Celery->>Task: Triggers background worker execution
    activate Task
    
    Task->>DB: Queries unprocessed training pairs (processed=False)
    activate DB
    DB-->>Task: Returns queryset of training records
    deactivate DB
    
    alt Unprocessed count < 10
        Task->>Task: Log message and skip training (insufficient batch size)
    else Unprocessed count >= 10
        Task->>Embed: Embeds query texts list
        activate Embed
        Embed-->>Task: Returns queries embeddings array
        Task->>Embed: Embeds candidate resolution texts list
        Embed-->>Task: Returns candidates embeddings array
        deactivate Embed
        
        Task->>Model: Initializes/loads current Keras model weights
        activate Model
        Task->>Model: Executes model.fit([queries, candidates], labels, epochs=3, batch=16)
        Model-->>Task: Model fitting finishes
        deactivate Model
        
        Task->>Storage: Writes weights file to models/reranker_weights.weights.h5
        Task->>DB: Bulk updates queryset to processed=True
    end
    
    Task-->>Celery: Worker returns success
    deactivate Task
```
