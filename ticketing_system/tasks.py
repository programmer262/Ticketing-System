from celery import shared_task
import numpy as np
import os
from django.conf import settings
from .models import Ticket, RerankerTrainingData
from .rag_pipeline import process_new_ticket_for_rag, get_embedding_model, get_keras_reranker
import logging

logger = logging.getLogger(__name__)

@shared_task
def process_rag_async(ticket_id):
    """
    Asynchronously processes a new ticket through the RAG pipeline.
    """
    try:
        ticket = Ticket.objects.get(id=ticket_id)
        process_new_ticket_for_rag(ticket)
    except Ticket.DoesNotExist:
        logger.error(f"Ticket {ticket_id} not found for RAG processing.")
    except Exception as e:
        logger.exception(f"Error in RAG task for ticket {ticket_id}: {e}")

@shared_task
def train_tf_reranker_task():
    """
    Placeholder for the training task mentioned in your plan.
    """
    data_points = RerankerTrainingData.objects.filter(processed=False)
    if data_points.count() < 10:  # Don't train on tiny batches
        logger.info("Not enough new training data to trigger retraining.")
        return

    logger.info(f"Starting reranker retraining with {data_points.count()} samples.")

    queries = []
    candidates = []
    labels = []

    for item in data_points:
        queries.append(item.query_text)
        candidates.append(item.candidate_text)
        labels.append(item.label)

    # 1. Vectorize text
    embed_model = get_embedding_model()
    query_embs = embed_model.encode(queries)
    cand_embs = embed_model.encode(candidates)

    # 2. Get/Build model
    model = get_keras_reranker()
    
    # 3. Train on current batch using binary crossentropy
    X_query = np.array(query_embs) 
    X_cand = np.array(cand_embs)
    y = np.array(labels)

    model.fit(
        [X_query, X_cand], 
        y, 
        epochs=3, 
        batch_size=16, 
        verbose=0
    )

    # 4. Save weights
    weights_dir = os.path.join(settings.BASE_DIR, 'models')
    if not os.path.exists(weights_dir):
        os.makedirs(weights_dir)
    
    weights_path = os.path.join(weights_dir, 'reranker_weights.weights.h5')
    model.save_weights(weights_path)

    # 5. Mark as processed
    data_points.update(processed=True)
    logger.info("Reranker model updated and weights saved.")