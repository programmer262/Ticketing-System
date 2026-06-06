# Celery Asynchronous Training Plan

We will integrate **Celery** into the Django project to handle the asynchronous training of the TensorFlow reranker professionally and seamlessly. Since you do not have Redis or RabbitMQ installed, we will use your existing SQLite database as the message broker.

## Proposed Architecture

### 1. Data Collection (`ticketing_system/models.py`)
- **[NEW] `RerankerTrainingData` model**: We will create a new database table to securely store the training pairs generated during human ticket resolution.
  - `query_text`: The text of the new ticket.
  - `candidate_text`: The text of the past closed ticket.
  - `label`: `1.0` for true matches, `0.0` for negative examples.
  - `processed`: Boolean flag to track which records have been trained on.

### 2. Celery Integration (`amineproject/celery.py` & `settings.py`)
- Install `celery` and `django-celery-results`.
- **Message Broker**: We will configure Celery to use the SQLite database as both the broker and result backend.
- Add the `amineproject/celery.py` file to initialize the Celery app and auto-discover tasks.
- Update `amineproject/__init__.py` to ensure Celery loads on Django startup.

### 3. Asynchronous Training Task (`ticketing_system/tasks.py`)
- **[NEW] `tasks.py`**: I will create a dedicated Celery task `@shared_task` named `train_tf_reranker_task`.
- **What the task does**:
  1. Fetches all unprocessed records from `RerankerTrainingData`.
  2. Compiles the TensorFlow model and executes `model.fit()` using the new data batch.
  3. Saves the updated weights to `model_weights.h5`.
  4. Marks the data batch as `processed=True`.

### 4. The Training Hook (`ticketing_system/views.py` & `rag_pipeline.py`)
- We will update the `async_train_hook_on_ticket_close` function to append the training data to the database and then call `train_tf_reranker_task.delay()`. This offloads the heavy lifting to the Celery worker queue instantly!

### 5. Model Loading (`ticketing_system/rag_pipeline.py`)
- Update `get_tf_reranker()` to automatically load `model_weights.h5` if the file exists, ensuring that the live pipeline immediately benefits from the latest asynchronous fine-tuning.

## Verification Plan
### Automated Tests
- Run database migrations.
- Spin up a test Celery worker.
- Close a ticket manually to verify that the Celery task receives the event and correctly trains the model in the background.
