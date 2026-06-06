import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'amineproject.settings')
django.setup()

from django.contrib.auth.models import User
from UserProfile.models import UserProfile
from ticketing_system.models import Ticket, TicketMessage
from ticketing_system.rag_pipeline import process_new_ticket_for_rag

def run_test():
    # 1. Setup Dummy Users
    user, _ = User.objects.get_or_create(username='testcustomer', defaults={'email': 'test@test.com', 'password': 'password'})
    profile, _ = UserProfile.objects.get_or_create(user=user, defaults={'role': 'Customer'})

    agent_user, _ = User.objects.get_or_create(username='testagent', defaults={'email': 'agent@test.com', 'password': 'password'})
    agent_profile, _ = UserProfile.objects.get_or_create(user=agent_user, defaults={'role': 'Agent'})

    # 2. Create a past closed ticket with a resolution
    print("Creating a past closed ticket...")
    past_ticket = Ticket.objects.create(customer=profile, title="My monitor is broken", status="Closed")
    TicketMessage.objects.create(ticket=past_ticket, sender=profile, message="The screen is completely black when I turn it on.")
    TicketMessage.objects.create(ticket=past_ticket, sender=agent_profile, message="Please check if the power cable is plugged in firmly. If it is, we will replace it.")

    # 3. Create a new similar ticket
    print("Creating a new similar ticket...")
    new_ticket = Ticket.objects.create(customer=profile, title="Monitor not working", status="Open")
    TicketMessage.objects.create(ticket=new_ticket, sender=profile, message="My screen is black and won't turn on.")

    # 4. Trigger the RAG Pipeline
    print("Processing RAG pipeline...")
    process_new_ticket_for_rag(new_ticket)

    # 5. Output the results
    new_ticket.refresh_from_db()
    print(f"\n--- Results ---")
    print(f"New Ticket Status: {new_ticket.status}")
    print("Messages on new ticket:")
    for msg in new_ticket.messages.all():
        role = msg.sender.role if msg.sender else 'None'
        print(f" - [{role}] {msg.message}")

    # Optionally, we can print the candidate scores
    print("\nCandidate Retrieval Scores:")
    for cand in new_ticket.rag_candidates.all():
        print(f" - Matched past ticket ID {cand.candidate_ticket.id} with Score: {cand.relevance_score:.4f}")

if __name__ == '__main__':
    run_test()
