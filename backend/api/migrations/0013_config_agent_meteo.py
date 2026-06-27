from django.db import migrations, models

import api.fields


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0012_configuration_email'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfigurationAgentEvenements',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('actif', models.BooleanField(default=False)),
                ('anthropic_api_key', api.fields.EncryptedTextField(blank=True, default='')),
                ('modele', models.CharField(default='claude-opus-4-8', max_length=50)),
                ('ville', models.CharField(blank=True, default='', max_length=120)),
                ('mois', models.IntegerField(blank=True, null=True)),
                ('annee', models.IntegerField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'db_table': 'configuration_agent_evenements'},
        ),
        migrations.CreateModel(
            name='ConfigurationMeteo',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('actif', models.BooleanField(default=False)),
                ('api_key', api.fields.EncryptedTextField(blank=True, default='')),
                ('ville', models.CharField(blank=True, default='', max_length=120)),
                ('mois', models.IntegerField(blank=True, null=True)),
                ('annee', models.IntegerField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'db_table': 'configuration_meteo'},
        ),
    ]
