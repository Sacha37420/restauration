"""Plat.photo (ImageField local) → Plat.photo_path (chemin dans storage).

Aucune migration de données : la colonne `photo` n'a jamais contenu de valeur
en base. Les uploads atterrissaient dans MEDIA_ROOT (= BASE_DIR/media, donc
dans le bind mount ./backend:/app, hors de tout volume), et leur lecture était
cassée — `config/urls.py` les servait via `static(settings.MEDIA_URL, …)`, qui
retourne une liste vide quand DEBUG=False, ce qui est le cas en déploiement.
Voir CLAUDE.md racine, section « Fichiers rasters / médias ».
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0023_stations_meteo'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='plat',
            name='photo',
        ),
        migrations.AddField(
            model_name='plat',
            name='photo_path',
            field=models.CharField(blank=True, default='', max_length=1024),
        ),
    ]
