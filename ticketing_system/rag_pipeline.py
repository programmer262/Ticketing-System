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
os.environ["TOKENIZERS_PARALLELISM"] = "false"

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
    output = keras.layers.Dense(1, activation='sigmoid', name="relevance_score")(dense2)
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
    try:
        nvidia_api_key = getattr(settings, 'NVIDIA_API_KEY', os.getenv('NVIDIA_API_KEY'))
        if not nvidia_api_key:
            raise ValueError("NVIDIA_API_KEY not configured in settings")
            
        llm = ChatNVIDIA(
            model="z-ai/glm-5.1", 
            temperature=0.1,  # Keep it low so the AI doesn't invent non-existent technical steps
            timeout=15  
        )
        
        # --- HIGHLY OPTIMIZED SYSTEM PROMPT ---
        system_prompt = (
            "You are an advanced AI Customer Support Engineer. Your goal is to resolve a new customer issue "
            "by adapting an approved, verified historical solution from a past resolved ticket.\n\n"
            "CRITICAL EXECUTION RULES:\n"
            "1. REFORMULATE & ADAPT: Do not blindly copy-paste the historical resolution. Rewrite it so that "
            "it directly addresses the wording, context, and specific problem of the CURRENT incoming issue.\n"
            "2. ANONYMIZE DATA: Look closely at the historical resolution. If it contains names, order IDs, "
            "ticket references, IP addresses, or specific dates belonging to the old ticket, strip them out "
            "or replace them with relevant generic placeholders or context from the new ticket.\n"
            "3. NO META-COMMENTARY: Speak directly to the customer. Never say things like 'Based on past tickets...' "
            "or 'According to our system history...'. The customer should feel like you are troubleshooting "
            "their issue live right now.\n"
            "4. TONE & LENGTH: Maintain an empathetic, professional, and reassuring tone. Be concise, actionable, "
            "and break down technical steps into clean, bulleted instructions."
        )
        
        # --- EXPLICIT DATA SEPARATION FOR THE CONTEXT WINDOW ---
        user_prompt = (
            f"### HISTORICAL VERIFIED RESOLUTION (FOUND IN KNOWLEDGE BASE):\n"
            f"{historical_resolution}\n\n"
            f"### CURRENT INCOMING CUSTOMER ISSUE:\n"
            f"{query_text}\n\n"
            f"Please generate the optimized, personalized support message for the customer:"
        )
        
        response = llm.invoke([("system", system_prompt), ("human", user_prompt)])
        print(response)
        return response.content
        
    except Exception as e:
        print(f"[RAG LLM FALLBACK] NVIDIA endpoint unreachable: {e}")
        return (
            f"Hello! We found a closely related ticket in our knowledge base. "
            f"Here is how it was handled previously:\n\n{historical_resolution}\n\n"
            f"Please review this guidance and reply back if you need alternative assistance."
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