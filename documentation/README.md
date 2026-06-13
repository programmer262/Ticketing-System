# Intelligent Ticketing System - Documentation Portal

Welcome to the documentation portal for the **Intelligent Ticketing System**. This system is a Django-based customer support platform enhanced with AI capabilities including **automated ticket classification (triage)** and a **Retrieval-Augmented Generation (RAG) auto-response pipeline** using a custom TensorFlow/Keras reranker.

---

## 📚 Documentation Modules

Click on any of the sections below to access the corresponding documentation page:

### 1. 🏗️ [System Architecture & Tech Stack](file:///c:/Users/lenovo/Desktop/amine-project/amineproject/documentation/architecture.md)
*Overview of the overall architecture, tech stack dependencies, and component relationships (featuring a Mermaid interaction diagram).*

### 2. 🗄️ [Database Schema & Models](file:///c:/Users/lenovo/Desktop/amine-project/amineproject/documentation/database_schema.md)
*Comprehensive documentation of the Django ORM database tables, relations, indexes, and custom fields used across both `UserProfile` and `ticketing_system` apps.*

### 3. 🤖 [AI Systems (Triage & RAG Reranker)](file:///c:/Users/lenovo/Desktop/amine-project/amineproject/documentation/ai_systems.md)
*Deep dive into the LLM-powered Ticket Triage system, the sentence embeddings generator, the custom Keras Reranker, and the LangChain/NVIDIA LLM response generator.*

### 4. ⚙️ [Celery Asynchronous Tasks & Training (Placeholder)](file:///c:/Users/lenovo/Desktop/amine-project/amineproject/documentation/celery_tasks.md)
*Details on the asynchronous settings and placeholder Celery tasks (which are currently inactive and not integrated into the active workflows).*

### 5. 👥 [User Roles & Workflows](file:///c:/Users/lenovo/Desktop/amine-project/amineproject/documentation/user_roles_workflows.md)
*Description of user permissions, routing, dashboards, and step-by-step user-flow actions for Customers, Agents, Supervisors, and the AI System Agent.*

### 6. 🚀 [Developer Setup & Operation Guide](file:///c:/Users/lenovo/Desktop/amine-project/amineproject/documentation/setup_and_operation.md)
*Step-by-step guides for installing dependencies, bootstrapping initial training datasets, running migrations, spinning up workers, and running the validation suite.*

---

## 🛠️ Main Tech Stack Reference
* **Backend Framework**: Django 6.0.5
* **Asynchronous Task Processing**: Celery 5.6.3 *(Configured as settings/task placeholders; not integrated into live workflows)*
* **Embedding Model**: SentenceTransformers (`all-MiniLM-L6-v2`)
* **Vector Match & Reranker**: Custom TensorFlow/Keras Sequential model
* **Large Language Models**: LangChain + NVIDIA AI Endpoints (`kimi-k2.6` for triage, `z-ai/glm-5.1` for RAG responses)
