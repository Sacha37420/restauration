from django.db import migrations

import api.fields


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0007_categorie_sous_categorie_plat'),
    ]

    operations = [
        migrations.AlterField(
            model_name='configurationstripe',
            name='stripe_secret_key',
            field=api.fields.EncryptedTextField(blank=True, default=''),
        ),
        migrations.AlterField(
            model_name='configurationstripe',
            name='stripe_webhook_secret',
            field=api.fields.EncryptedTextField(blank=True, default=''),
        ),
    ]
