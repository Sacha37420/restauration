from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0008_chiffrer_cles_stripe'),
    ]

    operations = [
        migrations.AddField(
            model_name='paiement',
            name='confirme_par',
            field=models.CharField(blank=True, default='', max_length=254),
        ),
    ]
