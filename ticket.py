import os
import csv
import django
from django.contrib.auth import get_user_model

from django.db import transaction

# Initialize Django environment settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amineproject.settings")
django.setup()

from ticketing_system.models import Ticket, TicketMessage, UserProfile, Category

def import_completed_tickets(file_path):
    User = get_user_model()
    
    print("[MIGRATION] Setting up agent profiles...")
    customer_user, _ = User.objects.get_or_create(username='historical_customer', defaults={'email': 'cust@old.local'})
    customer_profile, _ = UserProfile.objects.get_or_create(user=customer_user, defaults={'role': 'Customer'})
    
    agent_user, _ = User.objects.get_or_create(username='historical_agent', defaults={'email': 'agent@old.local'})
    agent_profile, _ = UserProfile.objects.get_or_create(user=agent_user, defaults={'role': 'Agent'})

    tickets_to_create = []
    skipped_count = 0

    print(f"[MIGRATION] Processing file: {file_path}")
    with open(file_path, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for index, row in enumerate(reader):
            # --- THE FILTER ---
            # Extract status (handles potential variations in CSV column casing)
            status_value = row.get('status', '').strip().lower()
            
            # Filter: Only keep 'closed' and 'resolved' tickets
            if status_value not in ['closed', 'resolved']:
                skipped_count += 1
                continue

            # 1. Clean row data variables
            title = f"{row.get('product', 'General Support')} Support Case"
            description = row.get('issue_description', '')
            resolution = row.get('resolution_notes', '')
            category_name = row.get('category', 'General')

            category_obj, _ = Category.objects.get_or_create(name=category_name)

            # 2. Instantiate the Ticket
            ticket = Ticket(
                title=title,
                status=status_value.capitalize(),
                category=category_obj,
                customer=customer_profile
            )
            
            tickets_to_create.append((ticket, description, resolution))

            # Batch save every 2000 records to maximize execution speed
            if len(tickets_to_create) >= 2000:
                _execute_bulk_save(tickets_to_create, customer_profile, agent_profile)
                tickets_to_create = []
                print(f"[MIGRATION] Checked {index + 1} rows... Imported a clean batch.")

        # Save remaining entries
        if tickets_to_create:
            _execute_bulk_save(tickets_to_create, customer_profile, agent_profile)

    print(f"\n[MIGRATION] Complete!")
    print(f"--> Successfully imported closed and resolved tickets.")
    print(f"--> Filtered out and skipped {skipped_count} non-completed tickets.")


def _execute_bulk_save(ticket_tuples, customer_profile, agent_profile):
    # We use a transaction atomic block to keep individual saves fast on SQLite
    with transaction.atomic():
        messages_to_create = []
        for ticket, description, resolution in ticket_tuples:
            # Save ticket individually to ensure it has an ID for the messages
            ticket.save()

            if description:
                messages_to_create.append(
                    TicketMessage(ticket=ticket, sender=customer_profile, message=description)
                )
            if resolution:
                messages_to_create.append(
                    TicketMessage(ticket=ticket, sender=agent_profile, message=resolution)
                )

        TicketMessage.objects.bulk_create(messages_to_create)

if __name__ == "__main__":
    import_completed_tickets("./customer_support_tickets_200k.csv")