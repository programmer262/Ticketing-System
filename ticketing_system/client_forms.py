from django import forms
from .models import Ticket, Category

class TicketForm(forms.ModelForm):
    # Add an explicit text field to capture the very first message/problem description
    initial_message = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'placeholder': 'Describe your issue in detail here...',
            'rows': 5
        }),
        label="Describe your problem"
    )

    class Meta:
        model = Ticket
        fields = ['title', 'category']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Database connection dropping'
            }),
            'category': forms.Select(attrs={
                'class': 'form-select'
            }),
        }