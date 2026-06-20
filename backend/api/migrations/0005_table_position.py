from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0004_seed_canaux_statuts'),
    ]

    operations = [
        migrations.AddField(
            model_name='tablerestaurant',
            name='pos_x',
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='tablerestaurant',
            name='pos_y',
            field=models.FloatField(blank=True, null=True),
        ),
    ]
