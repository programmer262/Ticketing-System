from django.contrib import admin
from .models import Category, Ticket, TicketMessage, RerankedQueue

# This lets us read/write conversation messages directly inside a Ticket's admin page
class TicketMessageInline(admin.TabularInline):
    model = TicketMessage
    extra = 1  # Provides 1 empty row by default to type a new message
    fields = ['sender', 'message', 'created_at']
    readonly_fields = ['created_at']

@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ['id', 'title', 'customer', 'category', 'priority', 'status', 'created_at']
    list_filter = ['status', 'priority', 'category']
    search_fields = ['title', 'customer__user__username']
    inlines = [TicketMessageInline]  # Injects the conversation thread right inside the ticket view!

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name']

@admin.register(RerankedQueue)
class RerankedQueueAdmin(admin.ModelAdmin):
    list_display = ['computed_rank', 'ticket', 'ai_relevance_score', 'target_agent']
    ordering = ['computed_rank']