# RAG System with Custom TensorFlow Reranker

This plan addresses the goal to implement a RAG system that uses a custom TensorFlow reranker (instead of Colbert or other libraries) to find relevant previous tickets, allowing an AI agent to automatically reply to similar new tickets.

## User Review Required

> [!IMPORTANT]
> Currently, `RerankedQueue` is used in `views.py` to dispatch tickets to human agents (by mapping `ticket` -> `target_agent`). Modifying `RerankedQueue` to serve as the storage for the VectorDB/Reranker will break this existing dispatch logic. 
> **Question:** Should we completely replace the current dispatch functionality of `RerankedQueue`, or should we create a *new* model (e.g., `TicketRetrievalCandidate`) for the RAG system and leave `RerankedQueue` for human agent dispatch?

> [!IMPORTANT]
> **Question:** How would you like the initial embeddings for the tickets to be generated before reranking? We can use an open-source embedding model (like `sentence-transformers`) to create the initial vectors, store them in the database, and then use your custom TensorFlow model to *rerank* the top K results. Is this approach acceptable?

> [!IMPORTANT]
> **Question:** Do you have an existing dataset to train the TensorFlow reranker, or should we build a simple un-trained/randomly initialized TensorFlow model for now that can be trained later?

## Proposed Changes

### 1. Model Updates (`ticketing_system/models.py`)
We will repurpose or add models to support the RAG workflow.
- **`TicketEmbedding`** [NEW]: A model to store the vector embeddings of ticket contents (e.g., using a `JSONField` or Postgres `pgvector` if applicable).
- **`RerankedQueue`** [MODIFY]: Update the model fields to store reranking results. For example, mapping a `source_ticket` to multiple `candidate_tickets` with their respective `ai_relevance_score` calculated by the TensorFlow model.

### 2. RAG & TensorFlow Reranker Module (`ticketing_system/rag_pipeline.py`)
- **[NEW] `rag_pipeline.py`**: A new file containing the logic for:
  - Generating initial embeddings for a new ticket.
  - Performing a vector search to find the top K similar past tickets.
  - Defining a custom `tf.keras.Model` that acts as the reranker (e.g., taking the embeddings or text of two tickets and outputting a relevance score).
  - Executing the TensorFlow model to rerank the candidates and store the results in `RerankedQueue`.

### 3. AI Agent Integration (`ticketing_system/views.py` or signals)
- **[MODIFY] `create_ticket_view`**: After a ticket is saved, trigger the RAG pipeline. If the highest `ai_relevance_score` from the TensorFlow reranker exceeds a certain confidence threshold, an `AI_Agent` user will automatically create a `TicketMessage` with a generated response based on the matched past ticket.

### 4. Dependencies
- Install `tensorflow` and `sentence-transformers` (or similar for base embeddings) via pip.

## Verification Plan
### Automated Tests
- Run `python manage.py makemigrations` and `python manage.py migrate` to ensure model changes are valid.
- Write a basic unit test to simulate creating a ticket, generating an embedding, and passing it through the TensorFlow reranker.

### Manual Verification
- Create a test ticket with a known issue.
- Create a second ticket with a similar issue and verify that the RAG pipeline computes the relevance score and the AI agent replies automatically.
