from django.db import migrations


UNITES = [
    ('kg', 'Kilogramme'),
    ('g', 'Gramme'),
    ('mg', 'Milligramme'),
    ('L', 'Litre'),
    ('mL', 'Millilitre'),
    ('cL', 'Centilitre'),
    ('pièce', 'Pièce / unité'),
    ('boîte', 'Boîte'),
    ('sachet', 'Sachet'),
    ('botte', 'Botte'),
    ('portion', 'Portion'),
]


def seed_unites(apps, schema_editor):
    Unite = apps.get_model('api', 'Unite')
    for nom, description in UNITES:
        Unite.objects.get_or_create(nom=nom, defaults={'description': description})


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_alter_canalcommande_id_alter_commande_id_and_more'),
    ]

    operations = [
        migrations.RunPython(seed_unites, migrations.RunPython.noop),
    ]
