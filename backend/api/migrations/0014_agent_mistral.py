from django.db import migrations, models

import api.fields
from api.models import DEFAULT_PROMPT_AGENT


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0013_config_agent_meteo'),
    ]

    operations = [
        migrations.RenameField(
            model_name='configurationagentevenements',
            old_name='anthropic_api_key',
            new_name='mistral_api_key',
        ),
        migrations.AlterField(
            model_name='configurationagentevenements',
            name='modele',
            field=models.CharField(default='mistral-large-latest', max_length=50),
        ),
        migrations.AddField(
            model_name='configurationagentevenements',
            name='system_prompt',
            field=models.TextField(default=DEFAULT_PROMPT_AGENT),
        ),
    ]
