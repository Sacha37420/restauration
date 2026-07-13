"""Sort la clé API, le modèle et l'activation de la config « événements » pour en faire
une ConfigurationMistral partagée par les trois usages (robot fournisseur, génération de
recettes, calendrier d'événements), et déplace le prompt dans PromptMistral.

L'ordre compte : on crée les tables, on RECOPIE la clé API existante, et seulement
ensuite on supprime les anciens champs — sinon la clé de l'utilisateur serait perdue.
"""
import api.fields
from django.db import migrations, models

from api import prompts


def reprendre_config_existante(apps, schema_editor):
    """La clé, le modèle et l'activation vivaient dans la config « événements ».
    Le prompt personnalisé, s'il différait du défaut, devient une surcharge."""
    Agent = apps.get_model('api', 'ConfigurationAgentEvenements')
    ConfigurationMistral = apps.get_model('api', 'ConfigurationMistral')
    PromptMistral = apps.get_model('api', 'PromptMistral')

    ancienne = Agent.objects.filter(pk=1).first()
    if ancienne is None:
        return

    ConfigurationMistral.objects.update_or_create(
        pk=1,
        defaults={
            'actif': ancienne.actif,
            'api_key': ancienne.mistral_api_key,
            'modele': ancienne.modele or 'mistral-large-latest',
        },
    )

    prompt = (ancienne.system_prompt or '').strip()
    if prompt and prompt != prompts.DEFAUT_EVENEMENTS.strip():
        PromptMistral.objects.update_or_create(
            usage=prompts.EVENEMENTS, defaults={'contenu': prompt})


def restaurer_config_evenements(apps, schema_editor):
    """Retour arrière : on remet la clé et le modèle sur la config « événements »."""
    Agent = apps.get_model('api', 'ConfigurationAgentEvenements')
    ConfigurationMistral = apps.get_model('api', 'ConfigurationMistral')
    PromptMistral = apps.get_model('api', 'PromptMistral')

    cfg = ConfigurationMistral.objects.filter(pk=1).first()
    if cfg is None:
        return

    surcharge = PromptMistral.objects.filter(usage=prompts.EVENEMENTS).first()
    Agent.objects.update_or_create(
        pk=1,
        defaults={
            'actif': cfg.actif,
            'mistral_api_key': cfg.api_key,
            'modele': cfg.modele,
            'system_prompt': surcharge.contenu if surcharge else prompts.DEFAUT_EVENEMENTS,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0020_fournisseur_rattachement_auto_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='ConfigurationMistral',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('actif', models.BooleanField(default=False)),
                ('api_key', api.fields.EncryptedTextField(blank=True, default='')),
                ('modele', models.CharField(default='mistral-large-latest', max_length=50)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'configuration_mistral',
            },
        ),
        migrations.CreateModel(
            name='PromptMistral',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('usage', models.CharField(choices=[('evenements', "Événements — calendrier de fréquentation d'une ville"), ('recette', 'Recettes — génération d’une recette originale'), ('robot_connexion', 'Robot fournisseur — 1. trouver la page de connexion'), ('robot_navigation', 'Robot fournisseur — 2. atteindre la liste des produits'), ('robot_extraction', 'Robot fournisseur — 3. extraire les produits'), ('robot_rapprochement', 'Robot fournisseur — 4. rattacher aux ingrédients')], max_length=40, unique=True)),
                ('contenu', models.TextField()),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'prompt_mistral',
                'ordering': ['usage'],
            },
        ),
        migrations.RunPython(reprendre_config_existante, restaurer_config_evenements),
        migrations.RemoveField(
            model_name='configurationagentevenements',
            name='actif',
        ),
        migrations.RemoveField(
            model_name='configurationagentevenements',
            name='mistral_api_key',
        ),
        migrations.RemoveField(
            model_name='configurationagentevenements',
            name='modele',
        ),
        migrations.RemoveField(
            model_name='configurationagentevenements',
            name='system_prompt',
        ),
    ]
