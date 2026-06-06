import os
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from .models import Ticket

# 1. Define the structural contract
class TicketAnalysis(BaseModel):
    priority: str = Field(
        description="The urgency level of the issue. Must be exactly one of: 'Low', 'Medium', or 'High'."
    )
    explanation: str = Field(
        description="A brief one-sentence reason why this priority level was assigned."
    )

def analyze_and_update_ticket(ticket_id, message_text):
    try:
        ticket = Ticket.objects.get(id=ticket_id)
    except Ticket.DoesNotExist:
        print(f"[AI TRIAGE ERROR] Ticket with ID {ticket_id} not found.")
        return
    # 2. Instantiate ChatNVIDIA pointing to Kimi-k2.6
    # We ensure temperature=0 for structured reliability and add max_tokens safety
    llm = ChatNVIDIA(
        model="moonshotai/kimi-k2.6",  # Ensure this matches your specific NVIDIA model identifier
        temperature=0,
        max_tokens=512 
    )
    
    # 3. Let ChatNVIDIA natively wrap the Pydantic model (No 'method' argument)
    structured_llm = llm.with_structured_output(TicketAnalysis)

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a strict, objective IT support triage specialist. Your job is to analyze incoming tickets "
            "and classify them into 'Low', 'Medium', or 'High' based on this exact operational threat matrix:\n\n"
            
            "CRITERIA FOR HIGH PRIORITY:\n"
            "- The core system or production database is completely down or inaccessible.\n"
            "- A major security incident or data breach (e.g., Ransomware, hacking, data leakage).\n"
            "- A critical business flow is totally blocked with zero workarounds (e.g., payment gateway completely failing).\n\n"
            
            "CRITERIA FOR MEDIUM PRIORITY:\n"
            "- A core feature is broken or throwing errors, BUT a temporary workaround exists.\n"
            "- Performance is severely degraded for multiple users, but the system is still online.\n"
            "- Important operations are delayed but not entirely blocked.\n\n"
            
            "CRITERIA FOR LOW PRIORITY:\n"
            "- How-to questions, general inquiries, or configuration advice.\n"
            "- Minor bugs, cosmetic/UI layout glitches, or minor feature requests.\n"
            "- Isolated issues affecting only a single user with negligible operational impact.\n\n"
            
            "Output your final decision using the mandated structured representation."
        )),
        ("human", "Ticket Title: {title}\nMessage: {message}")
    ])

    chain = prompt | structured_llm

    try:
        # 4. Invoke the chain securely
        ai_result = chain.invoke({"title": ticket.title, "message": message_text})
        
        # 5. Defensive structural validation check
        if ai_result is None:
            print("[AI TRIAGE WARNING] ChatNVIDIA returned None. Falling back to 'Medium'.")
            ticket.priority = 'Medium'
            ticket.save()
            return

        # Handle formatting mapping safety
        assigned_priority = ai_result.priority.capitalize()
        if assigned_priority not in ['Low', 'Medium', 'High']:
            assigned_priority = 'Medium'

        ticket.priority = assigned_priority
        ticket.save()

        print(f"\n[AI TRIAGE LOG] Ticket '{ticket.title}' classified as **{assigned_priority}** via Kimi-k2.6.")
        print(f"[AI REASONING] {ai_result.explanation}\n")

    except Exception as e:
        print(f"[AI TRIAGE CRITICAL ERROR] Execution failed: {e}")
        print("Safely falling back to default priority 'Low' to protect application flow.")
        ticket.priority = 'Low'
        ticket.save()