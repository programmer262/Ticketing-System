from celery import shared_task
import logging
import numpy as np
import os
from django.conf import settings
from .models import Ticket, RerankerTrainingData
from .rag_pipeline import process_new_ticket_for_rag, get_keras_reranker, get_embedding_model

logger = logging.getLogger(__name__)

@shared_task(name="ticketing_system.tasks.process_rag_async")
def process_rag_async(ticket_id):
    """
    Asynchronously processes a new ticket through the RAG pipeline.
    """
    try:
        ticket = Ticket.objects.get(id=ticket_id)
        process_new_ticket_for_rag(ticket)
        logger.info(f"Successfully processed RAG for ticket {ticket_id}")
    except Ticket.DoesNotExist:
        logger.error(f"RAG Task Error: Ticket {ticket_id} not found.")

@shared_task(name="ticketing_system.tasks.train_reranker_async")
def train_reranker_async():
    """
    Fetches unprocessed training data and fine-tunes the Keras Reranker.
    """
    data_points = RerankerTrainingData.objects.filter(processed=False)
    if data_points.count() < 10:  # Minimum batch size to justify training
        return "Not enough data to train yet."

    embed_model = get_embedding_model()
    reranker = get_keras_reranker()

    queries = []
    candidates = []
    labels = []

    for dp in data_points:
        queries.append(dp.query_text)
        candidates.append(dp.candidate_text)
        labels.append(dp.label)

    # Convert text to embeddings
    query_embs = embed_model.encode(queries)
    cand_embs = embed_model.encode(candidates)
    y = np.array(labels)

    # Train the model
    reranker.fit(
        [query_embs, cand_embs], 
        y, 
        epochs=3, 
        batch_size=4, 
        verbose=0
    )

    # Save weights
    weights_path = os.path.join(settings.BASE_DIR, 'models', 'reranker_weights.weights.h5')
    os.makedirs(os.path.dirname(weights_path), exist_ok=True)
    reranker.save_weights(weights_path)

    data_points.update(processed=True)
    return f"Trained on {len(data_points)} samples."