# Celery Asynchronous Tasks & Training (Placeholder Status)

> [!WARNING]
> **Celery is not integrated or active in the current live codebase.**
> While Celery settings exist in `settings.py` and task signatures are defined in `ticketing_system/tasks.py`, they function only as **inactive placeholders**. 
> Django does not load the Celery application on startup, and no views, models, or signals call these tasks. All processing (including RAG retrieval and AI Triage classification) currently runs **synchronously** in the HTTP request lifecycle.

---

## ⚙️ Configured Settings (Not Integrated)

The Celery settings are defined in the codebase but are not initialized on Django startup:
* **Celery Initialization**: Configured in [celery.py](file:///c:/Users/lenovo/Desktop/amine-project/amineproject/amineproject/celery.py).
* **Django Startup Link**: [amineproject/\_\_init\_\_.py](file:///c:/Users/lenovo/Desktop/amine-project/amineproject/amineproject/__init__.py) is currently empty and does not load the Celery app instance, meaning Celery will not auto-start or discover tasks unless this file is updated to import the app.
* **Broker & Result Backend settings** ([settings.py](file:///c:/Users/lenovo/Desktop/amine-project/amineproject/amineproject/settings.py)):
  ```python
  CELERY_BROKER_URL = 'redis://localhost:6379/0'
  CELERY_RESULT_BACKEND = 'redis://localhost:6379/0'
  CELERY_ACCEPT_CONTENT = ['json']
  CELERY_TASK_SERIALIZER = 'json'
  CELERY_RESULT_SERIALIZER = 'json'
  ```
  *(Note: Since Redis is not installed in the local environment, trying to start a Celery worker with these settings will fail unless overridden to use an SQLite transport broker).*

---

## 📋 Placeholder Tasks Directory

The placeholder tasks are defined in [ticketing_system/tasks.py](file:///c:/Users/lenovo/Desktop/amine-project/amineproject/ticketing_system/tasks.py):

### 1. `process_rag_async(ticket_id)`
Designed to run the RAG auto-response pipeline (`process_new_ticket_for_rag`) asynchronously in the background.
* **Status**: **Inactive**. In the active codebase, [views.py](file:///c:/Users/lenovo/Desktop/amine-project/amineproject/ticketing_system/views.py#L36) imports and runs `process_new_ticket_for_rag` synchronously inside `create_ticket_view`.
* **How to integrate**: To execute this asynchronously, update [views.py](file:///c:/Users/lenovo/Desktop/amine-project/amineproject/ticketing_system/views.py) to import the task and call it using:
  ```python
  from .tasks import process_rag_async
  process_rag_async.delay(ticket.id)
  ```

### 2. `train_tf_reranker_task()`
Designed to train the custom Keras Reranker model in the background using accumulated user interaction pairs.
* **Status**: **Inactive**. This training task is never called anywhere in the active views or signals.
* **Training Logic** (if integrated):
  1. **Record Check**: Queries unprocessed records in `RerankerTrainingData` where `processed=False`. Training is skipped if there are fewer than 10 samples to avoid overfitting.
  2. **Feature Extraction**: Converts query and candidate texts to dense 384-dimensional vectors using `SentenceTransformers`.
  3. **Fitting**: Compiles and trains the Keras sequential model (epochs=3, batch_size=16).
  4. **Persistence**: Saves the model weights to `models/reranker_weights.weights.h5`.
  5. **State update**: Marks database records as processed.
