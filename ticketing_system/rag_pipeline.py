import os
import numpy as np
import keras  # Modern Keras 3 syntax
from sentence_transformers import SentenceTransformer
from django.conf import settings
from django.contrib.auth import get_user_model
from langchain_nvidia_ai_endpoints import ChatNVIDIA 
from .models import Ticket, TicketRetrievalCandidate, TicketMessage, UserProfile, RerankerTrainingData

RERANK_THRESHOLD = 0.85
_embedding_model = None
_keras_reranker = None

def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    return _embedding_model

# --- Pure Keras Reranker Definition ---

def build_custom_keras_reranker(embedding_dim=384):
    """
    Builds a functional Keras model using native keras.layers and keras.Input.
    """
    input_query = keras.Input(shape=(embedding_dim,), name="query_embedding")
    input_doc = keras.Input(shape=(embedding_dim,), name="doc_embedding")
    
    # Concatenate the two embedding layers
    concat = keras.layers.Concatenate()([input_query, input_doc])
    
    # Dense hidden layers
    dense1 = keras.layers.Dense(128, activation='relu')(concat)
    dense2 = keras.layers.Dense(64, activation='relu')(dense1)
    
    # Output layer yielding a single score between 0 and 1
    output = keras.layers.Dense(1, activation='sigmoid', name="relevance_score")(dense2)
    
    # Instantiate and compile the Keras Model
    model = keras.Model(inputs=[input_query, input_doc], outputs=output)
    model.compile(
        optimizer='adam', 
        loss='binary_crossentropy', 
        metrics=['accuracy']
    )
    return model

def get_keras_reranker():
    global _keras_reranker
    if _keras_reranker is None:
        _keras_reranker = build_custom_keras_reranker()
        # Define a standard path for weights, perhaps in settings.BASE_DIR
        weights_path = os.path.join(settings.BASE_DIR, 'models', 'reranker_weights.weights.h5')
        if os.path.exists(weights_path):
            _keras_reranker.load_weights(weights_path)
    return _keras_reranker

def generate_llm_response(query_text, historical_resolution):
    """
    Uses the NVIDIA AI endpoint to generate a natural response based on retrieved context.
    """
    llm = ChatNVIDIA(model="moonshotai/kimi-k2.6", temperature=0.1)
    
    system_prompt = (
        "You are an AI support assistant. Use the provided historical resolution to "
        "answer the user's current problem. Be polite and concise."
    )
    user_prompt = f"Current Issue: {query_text}\n\nPast Successful Resolution: {historical_resolution}"
    
    response = llm.invoke([("system", system_prompt), ("human", user_prompt)])
    return response.content


# --- Optimized Core Pipeline ---

def process_new_ticket_for_rag(new_ticket):
    """
    The main RAG pipeline utilizing batched Keras inference.
    """
    # 1. Fetch Candidates from Database
    recent_closed = list(
        Ticket.objects.filter(status='Closed')
        .exclude(id=new_ticket.id)
        .prefetch_related('messages')
        .order_by('-updated_at')[:50]
    )
    if not recent_closed:
        return 

    # Prepare Query Text & Embedding
    initial_msg = new_ticket.messages.first()
    query_text = f"{new_ticket.title}\n{initial_msg.message if initial_msg else ''}"
    
    embed_model = get_embedding_model()
    query_emb = embed_model.encode(query_text)

    # 2. Batch Process Candidate Text Representations
    candidate_texts = []
    for candidate in recent_closed:
        cand_msgs = candidate.messages.all()
        cand_text = f"{candidate.title}\n{cand_msgs.first().message if cand_msgs.exists() else ''}"
        candidate_texts.append(cand_text)

    # Convert text to embeddings in a single batch
    doc_embs = embed_model.encode(candidate_texts) 

    # Replicate the query embedding matrix to match candidate count dimensions
    query_embs_batched = np.repeat(np.expand_dims(query_emb, axis=0), len(recent_closed), axis=0)

    # 3. Keras Batched Inference
    reranker = get_keras_reranker()
    
    # Keras .predict handles numpy arrays elegantly out of the box
    scores = reranker.predict([query_embs_batched, doc_embs], verbose=0).flatten()

    best_candidate = None
    highest_score = -1.0
    bulk_candidates_to_create = []

    # 4. Process Results and Stage for Bulk Insert
    for i, candidate in enumerate(recent_closed):
        score = float(scores[i])
        
        bulk_candidates_to_create.append(
            TicketRetrievalCandidate(
                new_ticket=new_ticket,
                candidate_ticket=candidate,
                relevance_score=score
            )
        )
        
        if score > highest_score:
            highest_score = score
            best_candidate = candidate

    # Execute a single database write hit
    TicketRetrievalCandidate.objects.bulk_create(bulk_candidates_to_create)

    # 5. Automated AI Action Guard
    if best_candidate and highest_score >= getattr(settings, 'RAG_RERANK_THRESHOLD', RERANK_THRESHOLD):
        resolution_msg = best_candidate.messages.exclude(sender__role='Customer').last()
        resolution_text = resolution_msg.message if resolution_msg else "The issue was resolved."
        
        try:
            ai_response = generate_llm_response(query_text, resolution_text)
        except Exception as e:
            print(f"[RAG ERROR] LLM Generation failed: {e}")
            ai_response = f"Based on a similar past ticket, this might help: {resolution_text}"
        
        User = get_user_model() 
        ai_user, _ = User.objects.get_or_create(username='ai_agent', defaults={'email': 'ai@system.local'})
        ai_profile, _ = UserProfile.objects.get_or_create(user=ai_user, defaults={'role': 'AI_Agent', 'status': 'Available'})
        
        TicketMessage.objects.create(
            ticket=new_ticket,
            sender=ai_profile,
            message=ai_response
        )
        
        new_ticket.status = 'Closed'
        new_ticket.save()

        # Log this as a positive training sample
        RerankerTrainingData.objects.create(
            query_text=query_text,
            candidate_text=f"{best_candidate.title}\n{resolution_text}",
            label=1.0
        )