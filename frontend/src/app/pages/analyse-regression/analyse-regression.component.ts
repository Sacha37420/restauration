import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DecimalPipe } from '@angular/common';
import { ApiService, CategoriePlat, RegressionResultat } from '../../core/api.service';

@Component({
  selector: 'app-analyse-regression',
  standalone: true,
  imports: [FormsModule, DecimalPipe],
  templateUrl: './analyse-regression.component.html',
  styleUrl: './analyse-regression.component.scss',
})
export class AnalyseRegressionComponent implements OnInit {
  private api = inject(ApiService);

  ville = '';
  annee: number = new Date().getFullYear();
  mois: number | null = null;
  cible = 'montant_ttc';
  categorie: number | null = null;   // null = global
  source = 'commandes';

  categories = signal<CategoriePlat[]>([]);
  loading = signal(false);
  error = signal<string | null>(null);
  resultat = signal<RegressionResultat | null>(null);

  cibles = [
    { v: 'montant_ttc', l: 'Valeur des ventes (TTC)' },
    { v: 'montant_ht', l: 'Valeur des ventes (HT)' },
    { v: 'quantite', l: 'Quantité vendue' },
  ];

  ngOnInit(): void {
    this.api.getCategories().subscribe({ next: c => this.categories.set(c) });
  }

  lancer(): void {
    if (!this.ville || !this.annee) { this.error.set('Renseigne une ville et une année.'); return; }
    this.loading.set(true); this.error.set(null); this.resultat.set(null);
    this.api.lancerRegression({
      ville: this.ville, annee: this.annee, mois: this.mois,
      cible: this.cible, categorie: this.categorie, source: this.source,
    }).subscribe({
      next: r => { this.resultat.set(r); this.loading.set(false); },
      error: err => { this.error.set(err.error?.detail ?? `Erreur ${err.status}`); this.loading.set(false); },
    });
  }
}
