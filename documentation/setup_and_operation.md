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

