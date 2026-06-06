from django.apps import AppConfig


class TicketingSystemConfig(AppConfig):
    name = 'ticketing_system'
    def ready(self):
        import ticketing_system.signals