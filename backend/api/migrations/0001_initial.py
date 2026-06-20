import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Fournisseur',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('nom', models.CharField(max_length=200)),
                ('email', models.CharField(blank=True, default='', max_length=254)),
                ('telephone', models.CharField(blank=True, default='', max_length=20)),
                ('commentaire', models.TextField(blank=True, default='')),
            ],
            options={'db_table': 'fournisseur', 'ordering': ['nom']},
        ),
        migrations.CreateModel(
            name='Unite',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('nom', models.CharField(max_length=10, unique=True)),
                ('description', models.TextField(blank=True, default='')),
            ],
            options={'db_table': 'unite', 'ordering': ['nom']},
        ),
        migrations.CreateModel(
            name='Recette',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('nom', models.CharField(max_length=200)),
                ('instructions_html', models.TextField()),
                ('temps_preparation', models.IntegerField()),
                ('nb_portions', models.IntegerField()),
            ],
            options={'db_table': 'recette', 'ordering': ['nom']},
        ),
        migrations.CreateModel(
            name='TableRestaurant',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('numero', models.IntegerField(unique=True)),
                ('token_qr', models.CharField(max_length=64, unique=True)),
                ('actif', models.BooleanField(default=True)),
            ],
            options={'db_table': 'table_restaurant', 'ordering': ['numero']},
        ),
        migrations.CreateModel(
            name='CanalCommande',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('nom', models.CharField(max_length=20, unique=True)),
                ('description', models.TextField(blank=True, default='')),
            ],
            options={'db_table': 'canal_commande', 'ordering': ['nom']},
        ),
        migrations.CreateModel(
            name='StatutCommande',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('nom', models.CharField(max_length=50, unique=True)),
                ('description', models.TextField(blank=True, default='')),
            ],
            options={'db_table': 'statut_commande', 'ordering': ['nom']},
        ),
        migrations.CreateModel(
            name='StatutPaiement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('nom', models.CharField(max_length=50, unique=True)),
                ('description', models.TextField(blank=True, default='')),
            ],
            options={'db_table': 'statut_paiement', 'ordering': ['nom']},
        ),
        migrations.CreateModel(
            name='Employe',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('role', models.CharField(max_length=20, choices=[
                    ('manager', 'Manager'), ('cuisinier', 'Cuisinier'), ('serveur', 'Serveur'),
                ])),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='employe',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'db_table': 'employe'},
        ),
        migrations.CreateModel(
            name='CompteClient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('telephone', models.CharField(blank=True, default='', max_length=20)),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='compte_client',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'db_table': 'compte_client'},
        ),
        migrations.CreateModel(
            name='Ingredient',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('nom', models.CharField(max_length=200, unique=True)),
                ('quantite_stock', models.DecimalField(decimal_places=3, default=0, max_digits=12)),
                ('seuil_alerte', models.DecimalField(blank=True, decimal_places=3, max_digits=12, null=True)),
                ('fournisseur', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='ingredients',
                    to='api.fournisseur',
                )),
                ('unite', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='ingredients',
                    to='api.unite',
                )),
            ],
            options={'db_table': 'ingredient', 'ordering': ['nom']},
        ),
        migrations.CreateModel(
            name='LigneRecette',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('quantite', models.DecimalField(decimal_places=3, max_digits=12)),
                ('recette', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='lignes_recette',
                    to='api.recette',
                )),
                ('ingredient', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='lignes_recette',
                    to='api.ingredient',
                )),
            ],
            options={'db_table': 'ligne_recette', 'unique_together': {('recette', 'ingredient')}},
        ),
        migrations.CreateModel(
            name='Plat',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('nom', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True, default='')),
                ('photo', models.ImageField(blank=True, null=True, upload_to='plats/')),
                ('prix_unitaire', models.DecimalField(decimal_places=2, max_digits=8)),
                ('sans_gluten', models.BooleanField(default=False)),
                ('halal', models.BooleanField(default=False)),
                ('vegetarien', models.BooleanField(default=False)),
                ('actif', models.BooleanField(default=True)),
                ('recette', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='plats',
                    to='api.recette',
                )),
            ],
            options={'db_table': 'plat', 'ordering': ['nom']},
        ),
        migrations.CreateModel(
            name='StockPlat',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('quantite_disponible', models.IntegerField(default=0)),
                ('date_production', models.DateTimeField()),
                ('plat', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='stocks_plat',
                    to='api.plat',
                )),
            ],
            options={'db_table': 'stock_plat', 'ordering': ['-date_production']},
        ),
        migrations.CreateModel(
            name='Commande',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('numero_table', models.IntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('canal', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='commandes',
                    to='api.canalcommande',
                )),
                ('statut', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='commandes',
                    to='api.statutcommande',
                )),
                ('table_restaurant', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='commandes',
                    to='api.tablerestaurant',
                )),
                ('compte_client', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='commandes',
                    to='api.compteclient',
                )),
            ],
            options={'db_table': 'commande', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='LigneCommande',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('quantite', models.IntegerField(default=1)),
                ('prix_unitaire_snapshot', models.DecimalField(decimal_places=2, max_digits=8)),
                ('commande', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='lignes_commande',
                    to='api.commande',
                )),
                ('plat', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='lignes_commande',
                    to='api.plat',
                )),
            ],
            options={'db_table': 'ligne_commande'},
        ),
        migrations.CreateModel(
            name='Paiement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('montant', models.DecimalField(decimal_places=2, max_digits=10)),
                ('methode', models.CharField(max_length=20)),
                ('transaction_id', models.CharField(blank=True, default='', max_length=255)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('commande', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='paiement',
                    to='api.commande',
                )),
                ('statut', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='paiements',
                    to='api.statutpaiement',
                )),
            ],
            options={'db_table': 'paiement', 'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='PlageTravail',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('debut', models.DateTimeField()),
                ('fin', models.DateTimeField()),
                ('note', models.TextField(blank=True, default='')),
                ('employe', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='plages_travail',
                    to='api.employe',
                )),
            ],
            options={'db_table': 'plage_travail', 'ordering': ['debut']},
        ),
        migrations.CreateModel(
            name='MouvementStock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('type', models.CharField(max_length=20, choices=[
                    ('entree', 'Entrée'), ('sortie', 'Sortie'), ('ajustement', 'Ajustement'),
                ])),
                ('quantite', models.DecimalField(decimal_places=3, max_digits=12)),
                ('date', models.DateTimeField(default=django.utils.timezone.now)),
                ('raison', models.TextField(blank=True, default='')),
                ('ingredient', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='mouvements_stock',
                    to='api.ingredient',
                )),
                ('employe', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='mouvements_stock',
                    to='api.employe',
                )),
            ],
            options={'db_table': 'mouvement_stock', 'ordering': ['-date']},
        ),
    ]
