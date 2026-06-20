from django.db import migrations


CANAUX = [
    ('sur_place', 'Commande passée en salle'),
    ('a_emporter', 'Commande à emporter'),
    ('livraison', 'Commande en livraison'),
]

STATUTS_COMMANDE = [
    ('en_attente', 'Commande reçue, en attente de traitement'),
    ('en_preparation', 'Commande prise en charge en cuisine'),
    ('prete', 'Commande prête à être servie'),
    ('servie', 'Commande remise au client'),
    ('annulee', 'Commande annulée'),
]

STATUTS_PAIEMENT = [
    ('en_attente', 'Paiement non encore effectué'),
    ('paye', 'Paiement validé'),
    ('rembourse', 'Paiement remboursé'),
]


def seed(apps, schema_editor):
    CanalCommande = apps.get_model('api', 'CanalCommande')
    StatutCommande = apps.get_model('api', 'StatutCommande')
    StatutPaiement = apps.get_model('api', 'StatutPaiement')

    for nom, desc in CANAUX:
        CanalCommande.objects.get_or_create(nom=nom, defaults={'description': desc})

    for nom, desc in STATUTS_COMMANDE:
        StatutCommande.objects.get_or_create(nom=nom, defaults={'description': desc})

    for nom, desc in STATUTS_PAIEMENT:
        StatutPaiement.objects.get_or_create(nom=nom, defaults={'description': desc})


def unseed(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_seed_unites'),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
