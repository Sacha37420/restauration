from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_configuration_stripe'),
    ]

    operations = [
        migrations.CreateModel(
            name='CategoriePlat',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(max_length=100)),
                ('ordre', models.IntegerField(default=0)),
            ],
            options={
                'db_table': 'categorie_plat',
                'ordering': ['ordre', 'nom'],
            },
        ),
        migrations.CreateModel(
            name='SousCategoriePlat',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nom', models.CharField(max_length=100)),
                ('ordre', models.IntegerField(default=0)),
                ('categorie', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sous_categories',
                    to='api.categorieplat',
                )),
            ],
            options={
                'db_table': 'sous_categorie_plat',
                'ordering': ['ordre', 'nom'],
            },
        ),
        migrations.AddField(
            model_name='plat',
            name='sous_categorie',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='plats',
                to='api.souscategorieplat',
            ),
        ),
        migrations.AlterModelOptions(
            name='plat',
            options={'ordering': ['sous_categorie__categorie__ordre', 'sous_categorie__ordre', 'nom']},
        ),
    ]
