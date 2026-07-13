"""Éclate le lien Ingredient → Fournisseur (1–1) en un vrai catalogue :
ArticleFournisseur (une référence achetable) + PrixArticle (tarif par palier,
historisé). Un ingrédient peut désormais être acheté chez plusieurs fournisseurs,
sous plusieurs marques et conditionnements, à des prix différents.

L'ordre des opérations compte : on crée les tables, on recopie la donnée
existante, et seulement ensuite on supprime Ingredient.fournisseur.
"""
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def creer_articles_depuis_fournisseur(apps, schema_editor):
    """Chaque ingrédient qui avait un fournisseur devient un article de ce
    fournisseur, marqué préféré. Le prix est inconnu : pas de PrixArticle."""
    Ingredient = apps.get_model('api', 'Ingredient')
    ArticleFournisseur = apps.get_model('api', 'ArticleFournisseur')

    for ingredient in Ingredient.objects.filter(fournisseur__isnull=False):
        ArticleFournisseur.objects.create(
            fournisseur_id=ingredient.fournisseur_id,
            ingredient_id=ingredient.id,
            libelle=ingredient.nom,
            unite_id=ingredient.unite_id,
            quantite_conditionnement=1,
            prefere=True,
            source='manuel',
        )


def restaurer_fournisseur(apps, schema_editor):
    """Retour arrière : on remet sur l'ingrédient le fournisseur de son article
    préféré (à défaut, le premier article trouvé)."""
    Ingredient = apps.get_model('api', 'Ingredient')
    ArticleFournisseur = apps.get_model('api', 'ArticleFournisseur')

    for ingredient in Ingredient.objects.all():
        articles = list(ArticleFournisseur.objects.filter(ingredient_id=ingredient.id))
        if not articles:
            continue
        prefere = next((a for a in articles if a.prefere), articles[0])
        ingredient.fournisseur_id = prefere.fournisseur_id
        ingredient.save(update_fields=['fournisseur'])


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0017_plat_taux_tva_venteagregee'),
    ]

    operations = [
        migrations.CreateModel(
            name='ArticleFournisseur',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('libelle', models.CharField(max_length=255)),
                ('reference', models.CharField(blank=True, default='', max_length=100)),
                ('ean', models.CharField(blank=True, default='', max_length=14)),
                ('marque', models.CharField(blank=True, default='', max_length=120)),
                ('conditionnement', models.CharField(blank=True, default='', max_length=100)),
                ('quantite_conditionnement', models.DecimalField(decimal_places=3, default=1, help_text="Contenu d'un conditionnement, exprimé dans `unite` (ex : 5 pour un carton de 5 kg).", max_digits=12)),
                ('disponible', models.BooleanField(default=True)),
                ('prefere', models.BooleanField(default=False)),
                ('url', models.CharField(blank=True, default='', max_length=500)),
                ('source', models.CharField(choices=[('manuel', 'Manuel'), ('csv', 'Import CSV'), ('robot', 'Robot fournisseur')], default='manuel', max_length=20)),
                ('synchronise_le', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('fournisseur', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='articles', to='api.fournisseur')),
                ('ingredient', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='articles', to='api.ingredient')),
                ('unite', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='articles', to='api.unite')),
            ],
            options={
                'db_table': 'article_fournisseur',
                'ordering': ['fournisseur__nom', 'libelle'],
            },
        ),
        migrations.CreateModel(
            name='PrixArticle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantite_min', models.DecimalField(decimal_places=3, default=1, help_text='Palier dégressif : tarif valable à partir de N conditionnements.', max_digits=12)),
                ('prix_ht', models.DecimalField(decimal_places=4, max_digits=10)),
                ('taux_tva', models.DecimalField(decimal_places=2, default=5.5, max_digits=5)),
                ('releve_le', models.DateTimeField(default=django.utils.timezone.now)),
                ('source', models.CharField(choices=[('manuel', 'Manuel'), ('csv', 'Import CSV'), ('robot', 'Robot fournisseur')], default='manuel', max_length=20)),
                ('article', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='prix', to='api.articlefournisseur')),
            ],
            options={
                'db_table': 'prix_article',
                'ordering': ['quantite_min', '-releve_le'],
            },
        ),
        migrations.AddConstraint(
            model_name='articlefournisseur',
            constraint=models.UniqueConstraint(condition=models.Q(('reference', ''), _negated=True), fields=('fournisseur', 'reference'), name='uniq_reference_par_fournisseur'),
        ),
        migrations.AddConstraint(
            model_name='prixarticle',
            constraint=models.UniqueConstraint(fields=('article', 'quantite_min', 'releve_le'), name='uniq_releve_par_palier'),
        ),
        migrations.RunPython(creer_articles_depuis_fournisseur, restaurer_fournisseur),
        migrations.RemoveField(
            model_name='ingredient',
            name='fournisseur',
        ),
    ]
