import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'amineproject.settings')
django.setup()

from django.contrib.auth.models import User
from UserProfile.models import UserProfile
from ticketing_system.models import Ticket, TicketMessage, Category
from ticketing_system.rag_pipeline import process_new_ticket_for_rag, bootstrap_training_data

def run_test():
    # 1. Setup Dummy Users
    user, _ = User.objects.get_or_create(username='testcustomer', defaults={'email': 'test@test.com', 'password': 'password'})
    profile, _ = UserProfile.objects.get_or_create(user=user, defaults={'role': 'Customer'})

    agent_user, _ = User.objects.get_or_create(username='testagent', defaults={'email': 'agent@test.com', 'password': 'password'})
    agent_profile, _ = UserProfile.objects.get_or_create(user=agent_user, defaults={'role': 'Agent'})

    # Setup Categories
    tech_support, _ = Category.objects.get_or_create(name="Technical Support")
    general, _ = Category.objects.get_or_create(name="General")
    payment_error, _ = Category.objects.get_or_create(name="Payment Error")

    # 2. Historical Data (Diverse samples for better Reranking)
    history = [
        {"c": tech_support, "t": "Monitor black", "q": "My screen won't turn on.", "r": "Ensure the power cable and HDMI are tight."},
        {"c": tech_support, "t": "VPN Fail", "q": "Cannot connect to VPN.", "r": "Restart your router and check your credentials."},
        {"c": tech_support, "t": "Outlook sync", "q": "Emails not arriving.", "r": "Check your offline mode and storage limit."},
        {"c": tech_support, "t": "Slow Wi-Fi", "q": "Internet is lagging.", "r": "Access points rebooted in your area."},
        
        {"c": general, "t": "Password reset", "q": "Locked out of Windows.", "r": "Reset successful. Temporary password sent to recovery mail."},
        {"c": general, "t": "Software request", "q": "Need Photoshop.", "r": "License approved. Install via Software Center."},
        {"c": general, "t": "MFA Setup", "q": "New phone, need MFA.", "r": "MFA reset. Scan the QR code at next login."},

        {"c": payment_error, "t": "Card Declined", "q": "Payment failed today.", "r": "Please check your bank's 3D Secure settings."},
        {"c": payment_error, "t": "Double Charge", "q": "Billed twice for August.", "r": "Refund processed for the duplicate charge."},
        {"c": payment_error, "t": "Refund Request", "q": "Want money back for credits.", "r": "Credits converted back to original payment method."},
    ]

    print("Creating historical closed tickets...")
    for item in history:
        t, created = Ticket.objects.get_or_create(
            title=item['t'],
            customer=profile,
            defaults={'status': 'Closed', 'category': item['c']}
        )
        if created:
            TicketMessage.objects.create(ticket=t, sender=profile, message=item['q'])
            TicketMessage.objects.create(ticket=t, sender=agent_profile, message=item['r'])

    # 3. Bootstrap Training Data (Pre-populates the Reranker DB)
    print("Generating training samples...")
    samples = bootstrap_training_data()
    print(f"Created {samples} training data points.")

    # 4. Create a new similar ticket to test RAG
    print("Creating a new similar ticket...")
    new_ticket = Ticket.objects.create(
        customer=profile, 
        title="Screen is dark", 
        status="Open", 
        category=tech_support
    )
    TicketMessage.objects.create(ticket=new_ticket, sender=profile, message="I can't see anything on my monitor despite it being plugged in.")

    # 5. Trigger the RAG Pipeline (Directly calling the function, bypassing Celery)
    print("Processing RAG pipeline...")
    process_new_ticket_for_rag(new_ticket)

    # 6. Output the results
    new_ticket.refresh_from_db()
    print(f"\n--- Results ---")
    print(f"New Ticket Status: {new_ticket.status}")
    print("Messages on new ticket:")
    for msg in new_ticket.messages.all():
        role = msg.sender.role if msg.sender else 'None'
        print(f" - [{role}] {msg.message}")

    print("\nCandidate Retrieval Scores:")
    for cand in new_ticket.rag_candidates.all():
        print(f" - Matched past ticket ID {cand.candidate_ticket.id} with Score: {cand.relevance_score:.4f}")
