# Developer Setup & Operation Guide

This document details the steps required to set up the development environment, initialize databases, ingest historical ticket data, and run verification tests for the **Intelligent Ticketing System**.

---

## 💻 1. Environment Setup

### Prerequisites
* **Python**: Version 3.10 to 3.13.
* **Database**: SQLite3 (bundled with Python).
* **Virtual Environment**: Recommending Python's built-in `venv` module.

### Step-by-Step Installation
1. Clone the repository and navigate to the project directory:
   ```bash
   cd amineproject
   ```
2. Activate your virtual environment (e.g. `amine-env`):
   * **Windows (Command Prompt)**:
     ```cmd
     ..\amine-env\Scripts\activate.bat
     ```
   * **Windows (PowerShell)**:
     ```powershell
     ..\amine-env\Scripts\Activate.ps1
     ```
   * **Linux / macOS**:
     ```bash
     source ../amine-env/bin/activate
     ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file at the root of the project to supply required AI API keys:
   ```env
   NVIDIA_API_KEY=nvapi-your-key-here
   ```

---

## 🗄️ 2. Database Initialization & Seed

1. Generate and apply database migrations to setup schemas:
   ```bash
   python manage.py makemigrations
   ```
   ```bash
   python manage.py migrate
   ```
2. Create a superuser account to access the Django admin panel (`/admin/`):
   ```bash
   python manage.py createsuperuser
   ```

---

## 📥 3. Data Migration (Historical Import)

The database can be seeded with historical ticket records to build a knowledge base for RAG.
1. Ensure the CSV dataset file `customer_support_tickets_200k.csv` is located at the root of the project directory.
2. Run the ingestion script:
   ```bash
   python ticket.py
   ```
   * **What it does**:
     * Parses the CSV.
     * Filters for closed or resolved tickets.
     * Imports ticket content, classifications, and historical replies.
     * Uses transaction blocks to process saves in batches of 2000 records, preventing database locks on SQLite.

---

## ⚙️ 4. Running the Application

### Running the Web Server
To start the Django local development server:
```bash
python manage.py runserver
```
Navigate to `http://127.0.0.1:8000/` in your browser.

### Running Celery Background Workers
To run the background task processor:
```bash
celery -A amineproject worker -l info
```
*(Note: Celery is configured in `settings.py` to use Redis as a broker. If Redis is unavailable, Celery task execution will degrade or fail unless modified to use the SQLite transport broker).*

---

## 🧪 5. Testing & Verification

### Running Unit Tests
To run the test suite:
```bash
python manage.py test
```

### Running the RAG Simulation Script
The simulation script `test_rag.py` creates a sandbox customer/agent, inserts small historical samples, and verifies that RAG auto-closes similar issues.
```bash
python test_rag.py
```

---

## ⚠️ 6. Troubleshooting & Known Issues

### 🔍 Issue 1: `ImportError: cannot import name 'bootstrap_training_data'`
* **Description**: Running `python test_rag.py` results in a compilation failure:
  ```text
  ImportError: cannot import name 'bootstrap_training_data' from 'ticketing_system.rag_pipeline'
  ```
* **Cause**: `test_rag.py` imports a function `bootstrap_training_data` from `ticketing_system.rag_pipeline` that is not defined in the pipeline code.
* **Workaround**: To fix the script, edit `test_rag.py` to comment out or delete the following sections:
  1. Remove `bootstrap_training_data` from the import statement on **line 10**:
     ```python
     # Before
     from ticketing_system.rag_pipeline import process_new_ticket_for_rag, bootstrap_training_data
     # After
     from ticketing_system.rag_pipeline import process_new_ticket_for_rag
     ```
  2. Comment out or delete the bootstrap block on **lines 52–55**:
     ```python
     # Comment out these lines
     # print("Generating training samples...")
     # samples = bootstrap_training_data()
     # print(f"Created {samples} training data points.")
     ```

### 🔌 Issue 2: Connection reset errors (10054) during `manage.py test`
* **Description**: Tests fail with `urllib3.exceptions.ProtocolError` or `requests.exceptions.ConnectionError` inside `ai_triage.py`.
* **Cause**: Django signals (`trigger_ai_triage`) run automatically whenever a new `TicketMessage` is saved in tests. The function `analyze_and_update_ticket` instantiates `ChatNVIDIA(...)` outside of standard error catch blocks, which initiates a live listing API request. In isolated sandbox environments (offline test suites), this request fails and crashes the test database teardown.
* **Workaround**: Ensure a valid `NVIDIA_API_KEY` is present in your environment/`.env`, or mock the `ChatNVIDIA` constructor inside the Django test suite to prevent live internet requests.
