from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ticketing_system', '0003_rerankertrainingdata'),
    ]

    operations = [
        migrations.AddField(
            model_name='ticket',
            name='triage_explanation',
            field=models.TextField(blank=True, default=''),
        ),
    ]
