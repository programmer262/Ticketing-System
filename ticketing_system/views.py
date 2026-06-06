from django.shortcuts import render, redirect,get_object_or_404
from django.contrib.auth.decorators import login_required,user_passes_test

from .client_forms import TicketForm
from .models import *


def is_customer(user):
    return user.is_authenticated and (user.profile.role == 'Customer' or user.is_superuser)

@login_required 
@user_passes_test(is_customer, login_url='/tickets/dashboard/')
def create_ticket_view(request):
    if request.method == 'POST':
        form = TicketForm(request.POST)
        if form.is_valid():
            # 1. Save the Ticket instance but don't commit to DB yet because we need to attach the customer
            ticket = form.save(commit=False)
            ticket.customer = request.user.profile  # Assign current logged-in user profile
            ticket.save()  # Now it saves to DB and gets its UUID!

            # 2. Extract the initial message from our cleaned form data
            message_text = form.cleaned_data['initial_message']

            # 3. Create the corresponding TicketMessage inside our Ticket folder
            TicketMessage.objects.create(
                ticket=ticket,
                sender=request.user.profile,
                message=message_text
            )

            # 4. Execute the RAG Pipeline to check for existing resolutions
            try:
                from .tasks import process_rag_async
                process_rag_async.delay(str(ticket.id))
            except Exception as e:
                # Log error but don't fail ticket creation
                print(f"Error in RAG pipeline: {e}")

            # Redirect to a success page or back to admin to view it
            return redirect('/tickets/'+ str(ticket.id))
    else:
        form = TicketForm()

    return render(request, 'Customer/ticket_form.html', {'form': form})
@login_required
@user_passes_test(is_customer,login_url='/tickets/workspace/')
def ticket_dashboard_view(request):
    # Fetch only the tickets belonging to the currently logged-in customer
    user_profile = request.user.profile
    tickets = Ticket.objects.filter(customer=user_profile).order_by('-created_at')

    # Handle Search Queries
    search_query = request.GET.get('search', '')
    if search_query:
        # Filter tickets by title containing the search query (case-insensitive)
        tickets = tickets.filter(title__icontains=search_query)

    return render(request, 'Customer/dashboard.html', {
        'tickets': tickets,
        'search_query': search_query
    })
@login_required
def ticket_detail_view(request, ticket_id):
    user_profile = request.user.profile
    
    # 1. Fetch the ticket by ID only first
    ticket = get_object_or_404(Ticket, id=ticket_id)
    
    # 2. Security Check: Allow access ONLY if they are the owner OR staff
    is_owner = (ticket.customer == user_profile)
    is_staff = (user_profile.role in ['Agent', 'Supervisor'] or request.user.is_superuser)
    
    if not (is_owner or is_staff):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("You do not have permission to view this ticket thread.")
    
    # 3. Handle incoming message responses
    if request.method == 'POST':
        reply_text = request.POST.get('message', '').strip()
        if reply_text:
            TicketMessage.objects.create(
                ticket=ticket,
                sender=user_profile,
                message=reply_text
            )
            
            # Smart Status Management:
            if user_profile.role == 'Customer':
                # If a customer replies, ensure it's marked Open for staff to see
                if ticket.status == 'Closed':
                    ticket.status = 'Open'
                    ticket.save()
            elif user_profile.role in ['Agent', 'Supervisor']:
                # If staff replies, automatically move it to 'In Progress'
                if ticket.status == 'Open':
                    ticket.status = 'In Progress'
                    ticket.save()
                    
            return redirect('ticket_detail', ticket_id=ticket.id)

    messages = ticket.messages.all().order_by('created_at')
    
    return render(request, 'Customer/ticket_detail.html', {
        'ticket': ticket,
        'messages': messages
    })

# Access control checks
def is_supervisor(user):
    return user.is_authenticated and (user.profile.role == 'Supervisor' or user.is_superuser)

def is_agent_or_above(user):
    return user.is_authenticated and (user.profile.role in ['Agent', 'Supervisor'] or user.is_superuser)


@login_required
@user_passes_test(is_supervisor, login_url='/accounts/login/')
def dispatch_dashboard_view(request):
    """
    SUPERVISOR VIEW: Shows all unassigned and assigned tickets.
    Allows the supervisor to pick an agent and dispatch the ticket.
    """
    if request.method == 'POST':
        ticket_id = request.POST.get('ticket_id')
        agent_profile_id = request.POST.get('agent_id')
        
        ticket = get_object_or_404(Ticket, id=ticket_id)
        agent = get_object_or_404(UserProfile, id=agent_profile_id, role='Agent')
        
        # Calculate a rank number based on how many tickets this agent already has
        existing_count = RerankedQueue.objects.filter(target_agent=agent).count()
        computed_rank = existing_count + 1

        # Create or update the dispatch queue entry
        RerankedQueue.objects.update_or_create(
            ticket=ticket,
            defaults={
                'ai_relevance_score': 1.0,  # Placeholder or inherited from AI triage
                'computed_rank': computed_rank,
                'target_agent': agent
            }
        )
        
        # Update ticket status to reflect work has begun
        ticket.status = 'In Progress'
        ticket.save()
        
        return redirect('dispatch_dashboard')

    # Get data to build the supervisor interface
    all_tickets = Ticket.objects.all().order_by('-created_at')
    human_agents = UserProfile.objects.filter(role='Agent') # List of available agents to assign to

    return render(request, 'Agents/agent_dispatch.html', {
        'all_tickets': all_tickets,
        'human_agents': human_agents,
    })


@login_required
@user_passes_test(is_agent_or_above, login_url='/accounts/login/')
def agent_workspace_view(request):
    """
    HUMAN AGENT VIEW: Shows only tickets explicitly dispatched to this agent
    by the supervisor.
    """
    agent_profile = request.user.profile
    my_dispatched_tickets = RerankedQueue.objects.filter(target_agent=agent_profile).order_by('computed_rank')

    return render(request, 'Agents/agent_workspace.html', {
        'my_queue': my_dispatched_tickets
    })