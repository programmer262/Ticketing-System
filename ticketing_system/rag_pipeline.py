import os
import numpy as np
import keras
from sentence_transformers import SentenceTransformer
from django.conf import settings
from django.contrib.auth import get_user_model
from langchain_nvidia_ai_endpoints import ChatNVIDIA 
from .models import Ticket, TicketRetrievalCandidate, TicketMessage, UserProfile, RerankerTrainingData

RERANK_THRESHOLD = 0.5
EXACT_TITLE_MATCH_SCORE = 0.95
HUMAN_AGENT_ROLES = ('Agent', 'Supervisor')
_embedding_model = None
_keras_reranker = None


def _get_resolution_message(candidate_ticket):
    """
    Return the closing resolution message from a closed candidate ticket.
    Prefers the last message from a human agent (Agent or Supervisor).
    Falls back to the last AI_Agent message only when no human agent replied.
    """
    messages = candidate_ticket.messages.select_related('sender')

    human_msg = messages.filter(sender__role__in=HUMAN_AGENT_ROLES).last()
    if human_msg:
        return human_msg

    return messages.filter(sender__role='AI_Agent').last()


def _cosine_similarity(vec_a, vec_b):
    a = np.asarray(vec_a, dtype=np.float32)
    b = np.asarray(vec_b, dtype=np.float32)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _reranker_weights_path():
    return os.path.join(settings.BASE_DIR, 'models', 'reranker_weights.weights.h5')


def _reranker_weights_loaded():
    return os.path.exists(_reranker_weights_path())

def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    return _embedding_model

def build_custom_keras_reranker(embedding_dim=384):
    input_query = keras.Input(shape=(embedding_dim,), name="query_embedding")
    input_doc = keras.Input(shape=(embedding_dim,), name="doc_embedding")
    concat = keras.layers.Concatenate()([input_query, input_doc])
    dense1 = keras.layers.Dense(128, activation='relu')(concat)
    dense2 = keras.layers.Dense(64, activation='relu')(dense1)
    output = keras.layers.Dense(4, activation='sigmoid', name="relevance_score")(dense2)
    model = keras.Model(inputs=[input_query, input_doc], outputs=output)
    model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
    return model

def get_keras_reranker():
    global _keras_reranker
    if _keras_reranker is None:
        _keras_reranker = build_custom_keras_reranker()
        weights_path = _reranker_weights_path()
        if os.path.exists(weights_path):
            _keras_reranker.load_weights(weights_path)
    return _keras_reranker

def generate_llm_response(query_text, historical_resolution):
    """
    Tries to use the NVIDIA endpoint. If Windows blocks it, falls back to a template.
    """
    try:
        nvidia_api_key = getattr(settings, 'NVIDIA_API_KEY', os.getenv('NVIDIA_API_KEY'))
        if not nvidia_api_key:
            raise ValueError("NVIDIA_API_KEY not configured in settings")
            
        llm = ChatNVIDIA(
            model="z-ai/glm-5.1", 
            temperature=0.1,

            timeout=30  # Don't hang forever
        )
        
        system_prompt = (
            "You are an AI support assistant. Use the provided historical resolution to "
            "answer the user's current problem. Be polite and concise."
            f"Here is the different resolved tickets:{historical_resolution} and the answer you provide him with answer based on the history knowing that the answer needs to be the same just adapted to the user question or query"
        )
        user_prompt = f"Current Issue: {query_text}\n\n"
        
        response = llm.invoke([("system", system_prompt), ("human", user_prompt)])
        print(response)
        return response["messages"][-1].content
        
    except Exception as e:
        print(f"[RAG LLM FALLBACK] NVIDIA endpoint unreachable: {e}")
        # Template fallback — no network needed
        return (
            f"Hello! We found a similar resolved ticket in our system. "
            f"The previous resolution was: {historical_resolution}\n\n"
            f"Please review this and let us know if it resolves your issue, "
            f"or reply if you need further assistance."
        )

def process_new_ticket_for_rag(new_ticket):
    """
    Main RAG pipeline. Wrapped so it NEVER crashes ticket submission.
    """
    print(f"[RAG PIPELINE] Starting retrieval for ticket '{new_ticket.title}' ({new_ticket.id}).")
    try:
        _process_new_ticket_for_rag_core(new_ticket)
    except Exception as e:
        print(f"[RAG PIPELINE ERROR] {e}")
        # Pipeline failed, but ticket remains open for human agents. No crash.

def _process_new_ticket_for_rag_core(new_ticket):
    # 1. Fetch Candidates
    recent_closed = list(
        Ticket.objects.filter(status='Closed', category=new_ticket.category)
        .exclude(id=new_ticket.id)
        .prefetch_related('messages')
        .order_by('-updated_at')[:50]
    )
    if not recent_closed:
        category_name = new_ticket.category.name if new_ticket.category else "None"
        print(
            f"[RAG PIPELINE] No closed tickets in category '{category_name}' — skipping retrieval."
        )
        return 

    # Prepare Query
    initial_msg = new_ticket.messages.first()
    query_text = f"{new_ticket.title}\n{initial_msg.message if initial_msg else ''}"
    
    embed_model = get_embedding_model()
    query_emb = embed_model.encode(query_text)

    # 2. Batch Embed Candidates
    candidate_texts = []
    for candidate in recent_closed:
        cand_msgs = candidate.messages.all()
        cand_text = f"{candidate.title}\n{cand_msgs.first().message if cand_msgs.exists() else ''}"
        candidate_texts.append(cand_text)

    doc_embs = embed_model.encode(candidate_texts) 
    query_embs_batched = np.repeat(np.expand_dims(query_emb, axis=0), len(recent_closed), axis=0)

    # 3. Score candidates: cosine similarity from embeddings, optionally blended with Keras reranker
    keras_scores = None
    if _reranker_weights_loaded():
        reranker = get_keras_reranker()
        keras_scores = reranker.predict([query_embs_batched, doc_embs], verbose=0).flatten()

    best_candidate = None
    highest_score = -1.0
    bulk_candidates_to_create = []

    new_title_norm = new_ticket.title.strip().lower()

    for i, candidate in enumerate(recent_closed):
        cos_score = _cosine_similarity(query_emb, doc_embs[i])
        if keras_scores is not None:
            score = max(float(keras_scores[i]), cos_score)
        else:
            score = cos_score

        if new_title_norm == candidate.title.strip().lower():
            score = max(score, EXACT_TITLE_MATCH_SCORE)

        print(
            f"[RAG PIPELINE] Candidate '{candidate.title}': "
            f"cosine={cos_score:.3f}, final={score:.3f}"
            + (f", keras={float(keras_scores[i]):.3f}" if keras_scores is not None else "")
        )

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

    TicketRetrievalCandidate.objects.bulk_create(bulk_candidates_to_create)
    print(
        f"[RAG PIPELINE] Scored {len(recent_closed)} candidate(s); "
        f"best match '{best_candidate.title}' score={highest_score:.3f}."
    )

    # 4. Auto-Response Guard
    threshold = getattr(settings, 'RAG_RERANK_THRESHOLD', RERANK_THRESHOLD)
    if best_candidate and highest_score >= threshold:
        resolution_msg = _get_resolution_message(best_candidate)
        if resolution_msg:
            ai_response = generate_llm_response(query_text, resolution_msg.message)
            resolution_text = ai_response
        else:
            resolution_text = "The issue was resolved."
            ai_response = generate_llm_response(query_text, resolution_text)
        
        User = get_user_model() 
        ai_user, _ = User.objects.get_or_create(
            username='ai_agent', 
            defaults={'email': 'ai@system.local'}
        )
        ai_profile, _ = UserProfile.objects.get_or_create(
            user=ai_user, 
            defaults={'role': 'AI_Agent', 'status': 'Available'}
        )
        
        TicketMessage.objects.create(
            ticket=new_ticket,
            sender=ai_profile,
            message=ai_response
        )
        
        new_ticket.status = 'Closed'
        new_ticket.save()

        RerankerTrainingData.objects.create(
            query_text=query_text,
            candidate_text=f"{best_candidate.title}\n{resolution_text}",
            label=1.0
        )
        print(
            f"[RAG PIPELINE] Auto-resolved ticket '{new_ticket.title}' "
            f"using candidate '{best_candidate.title}' (score={highest_score:.3f})."
        )
    else:
        print(
            f"[RAG PIPELINE] Best score {highest_score:.3f} below threshold {threshold:.2f} "
            f"— ticket left open for human agents."
        )