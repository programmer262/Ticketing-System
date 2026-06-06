from django.db import models
from django.contrib.auth.models import User

class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('Customer', 'Customer'),
        ('Agent', 'Human Agent'),
        ('Supervisor', 'Supervisor'),
        ('AI_Agent', 'AI System Agent'),
    ]

    STATUS_CHOICES = [
        ('Available', 'Available'),
        ('Busy', 'Busy'),
        ('Offline', 'Offline'),
    ]

    # Links directly to Django's built-in User (handles password, username, email)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='Customer')
    
    # --- Agent Configuration fields ---
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Offline')
    max_ticket_capacity = models.IntegerField(default=5)

    def __str__(self):
        return f"{self.user.username} ({self.role})"