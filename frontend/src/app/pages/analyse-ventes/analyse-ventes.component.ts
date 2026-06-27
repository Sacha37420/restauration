import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DecimalPipe } from '@angular/common';
import { ApiService, VenteAgregee, CategoriePlat } from '../../core/api.service';

@Component({
  selector: 'app-analyse-ventes',
  standalone: true,
  imports: [FormsModule, DecimalPipe],
  templateUrl: './analyse-ventes.component.html',
  styleUrl: './analyse-ventes.component.scss',
})
export class AnalyseVentesComponent implements OnInit {
  private api = inject(ApiService);

  annee: number = new Date().getFullYear();
  mois: number | null = null;
  source = '';

  items = signal<VenteAgregee[]>([]);
  categories = signal<CategoriePlat[]>([]);
  loading = signal(false);
  error = signal<string | null>(null);
  message = signal<string | null>(null);

  editing = signal<VenteAgregee | null>(null);
  fichier: File | null = null;

  ngOnInit(): void {
    this.api.getCategories().subscribe({ next: c => this.categories.set(c) });
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.getVentes({ annee: this.annee, mois: this.mois ?? undefined, source: this.source || undefined }).subscribe({
      next: v => { this.items.set(v); this.loading.set(false); },
      error: err => { this.error.set(`Erreur ${err.status}`); this.loading.set(false); },
    });
  }

  recalculer(): void {
    this.loading.set(true); this.error.set(null); this.message.set(null);
    this.api.recalculerVentesCommandes({ annee: this.annee, mois: this.mois }).subscribe({
      next: r => { this.message.set(r.detail); this.loading.set(false); this.load(); },
      error: err => { this.error.set(err.error?.detail ?? `Erreur ${err.status}`); this.loading.set(false); },
    });
  }

  onFichier(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    this.fichier = input.files?.[0] ?? null;
  }
  importer(): void {
    if (!this.fichier) { this.error.set('Sélectionne un fichier .xlsx.'); return; }
    this.loading.set(true); this.error.set(null); this.message.set(null);
    this.api.importerVentesExcel(this.fichier).subscribe({
      next: r => { this.message.set(r.detail); this.fichier = null; this.loading.set(false); this.load(); },
      error: err => { this.error.set(err.error?.detail ?? `Erreur ${err.status}`); this.loading.set(false); },
    });
  }
  telechargerModele(): void {
    this.api.telechargerTemplateVentes().subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = 'modele_ventes.xlsx'; a.click();
        setTimeout(() => URL.revokeObjectURL(url), 10000);
      },
    });
  }

  // Saisie manuelle
  nouveau(): void {
    this.editing.set({ date: '', categorie: null, montant_ht: 0, montant_ttc: 0, quantite: 0, source: 'manuel' });
  }
  editer(v: VenteAgregee): void { this.editing.set({ ...v }); }
  enregistrer(): void {
    const v = this.editing(); if (!v || !v.date) { this.error.set('Date requise.'); return; }
    const obs = v.id ? this.api.updateVente(v.id, v) : this.api.createVente(v);
    obs.subscribe({
      next: () => { this.editing.set(null); this.load(); },
      error: err => this.error.set(err.error ? JSON.stringify(err.error) : `Erreur ${err.status}`),
    });
  }
  supprimer(v: VenteAgregee): void {
    if (!v.id || !confirm('Supprimer cette ligne ?')) return;
    this.api.deleteVente(v.id).subscribe({ next: () => this.load() });
  }
}
