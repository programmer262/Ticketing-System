import uuid
from django.db import models
from UserProfile.models import UserProfile

class Category(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Ticket(models.Model):
    PRIORITY_CHOICES = [
        ('Low', 'Low'),
        ('Medium', 'Medium'),
        ('High', 'High'),
    ]
    STATUS_CHOICES = [
        ('Open', 'Open'),
        ('In Progress', 'In Progress'),
        ('Closed', 'Closed'),
    ]

    # Secure UUID primary key prevents URL guessing
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='tickets')
    title = models.CharField(max_length=100)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, blank=True, null=True, related_name='tickets')
    
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='Low')
    triage_explanation = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Open')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} ({self.status})"


class TicketMessage(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(UserProfile, on_delete=models.SET_NULL, null=True, related_name='sent_messages')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at'] # Ensures conversations read top-to-bottom chronologically

    def __str__(self):
        return f"Msg by {self.sender.user.username if self.sender else 'System'} on Ticket {self.ticket.id}"


class RerankedQueue(models.Model):
    ticket = models.OneToOneField(Ticket, on_delete=models.CASCADE, related_name='queue_entry')
    ai_relevance_score = models.FloatField()
    computed_rank = models.IntegerField()
    target_agent = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name='assigned_queue')

    class Meta:
        ordering = ['computed_rank']

    def __str__(self):
        return f"Rank {self.computed_rank} -> {self.ticket.title}"


class TicketRetrievalCandidate(models.Model):
    new_ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='rag_candidates')
    candidate_ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='retrieved_for')
    relevance_score = models.FloatField(default=0.0)

    class Meta:
        ordering = ['-relevance_score']

    def __str__(self):
        return f"Candidate for {self.new_ticket.id} -> {self.candidate_ticket.id} (Score: {self.relevance_score})"

class RerankerTrainingData(models.Model):
    """
    Stores pairs of queries and successful resolutions to train the Keras reranker.
    """
    query_text = models.TextField()
    candidate_text = models.TextField()
    label = models.FloatField(help_text="1.0 for relevant, 0.0 for irrelevant")
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)