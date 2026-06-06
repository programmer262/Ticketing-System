from django.apps import AppConfig


class UserprofileConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'UserProfile'  # Matches your app's directory name

    def ready(self):
        # This imports the signals when Django starts up
        import UserProfile.signals