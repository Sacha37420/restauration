import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0014_agent_mistral'),
    ]

    operations = [
        migrations.CreateModel(
            name='Evenement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ville', models.CharField(max_length=120)),
                ('titre', models.CharField(max_length=255)),
                ('date_debut', models.DateField()),
                ('date_fin', models.DateField()),
                ('surplus_frequentation', models.IntegerField(default=0)),
                ('confiance', models.CharField(blank=True, choices=[('faible', 'Faible'), ('moyenne', 'Moyenne'), ('elevee', 'Élevée')], default='', max_length=10)),
                ('source', models.CharField(default='manuel', max_length=20)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={'db_table': 'evenement', 'ordering': ['date_debut', 'titre']},
        ),
    ]
