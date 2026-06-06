from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import TicketMessage
from .ai_triage import analyze_and_update_ticket

@receiver(post_save, sender=TicketMessage)
def trigger_ai_triage(sender, instance, created, **kwargs):
    """
    This signal listens to the TicketMessage model. 
    When the FIRST message of a ticket is saved, it passes it to the AI.
    """
    if created:
        ticket = instance.ticket
        
        # We only want to run the triage optimization if this is the very first message 
        # (meaning the ticket was just opened by the customer)
        is_first_message = ticket.messages.count() == 1
        
        if is_first_message:
            # Run the LangChain function we just wrote
            analyze_and_update_ticket(ticket.id, instance.message)