import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DecimalPipe } from '@angular/common';
import { ApiService, Evenement } from '../../core/api.service';

@Component({
  selector: 'app-analyse-evenements',
  standalone: true,
  imports: [FormsModule, DecimalPipe],
  templateUrl: './analyse-evenements.component.html',
  styleUrl: './analyse-evenements.component.scss',
})
export class AnalyseEvenementsComponent implements OnInit {
  private api = inject(ApiService);

  ville = '';
  annee: number = new Date().getFullYear();
  mois: number | null = null;

  items = signal<Evenement[]>([]);
  loading = signal(false);
  error = signal<string | null>(null);

  // Édition / ajout manuel
  editing = signal<Evenement | null>(null);

  // Propositions Mistral (aperçu non enregistré)
  propositions = signal<Evenement[] | null>(null);
  propLoading = signal(false);
  propError = signal<string | null>(null);

  ngOnInit(): void { this.load(); }

  load(): void {
    this.loading.set(true);
    this.error.set(null);
    this.api.getEvenements({ ville: this.ville, annee: this.annee, mois: this.mois ?? undefined }).subscribe({
      next: e => { this.items.set(e); this.loading.set(false); },
      error: err => { this.error.set(`Erreur ${err.status}`); this.loading.set(false); },
    });
  }

  nouveau(): void {
    this.editing.set({
      ville: this.ville, titre: '', date_debut: '', date_fin: '',
      surplus_frequentation: 0, confiance: '', source: 'manuel',
    });
  }
  editer(e: Evenement): void { this.editing.set({ ...e }); }
  annulerEdition(): void { this.editing.set(null); }

  enregistrer(): void {
    const e = this.editing();
    if (!e || !e.titre || !e.date_debut) { this.error.set('Titre et date de début requis.'); return; }
    e.date_fin = e.date_fin || e.date_debut;
    const obs = e.id ? this.api.updateEvenement(e.id, e) : this.api.createEvenement(e);
    obs.subscribe({
      next: () => { this.editing.set(null); this.load(); },
      error: err => this.error.set(err.error ? JSON.stringify(err.error) : `Erreur ${err.status}`),
    });
  }

  supprimer(e: Evenement): void {
    if (!e.id || !confirm(`Supprimer « ${e.titre} » ?`)) return;
    this.api.deleteEvenement(e.id).subscribe({ next: () => this.load() });
  }

  // ── Mistral ──
  completerMistral(): void {
    if (!this.ville || !this.annee) { this.propError.set('Renseigne une ville et une année.'); return; }
    this.propLoading.set(true);
    this.propError.set(null);
    this.api.proposerEvenementsMistral({ ville: this.ville, mois: this.mois, annee: this.annee }).subscribe({
      next: r => { this.propositions.set(r.evenements.map(x => ({ ...x }))); this.propLoading.set(false); },
      error: err => { this.propError.set(err.error?.detail ?? `Erreur ${err.status}`); this.propLoading.set(false); },
    });
  }
  retirerProposition(i: number): void {
    this.propositions.update(p => (p ?? []).filter((_, idx) => idx !== i));
  }
  annulerPropositions(): void { this.propositions.set(null); this.propError.set(null); }
  enregistrerPropositions(): void {
    const props = this.propositions();
    if (!props?.length) return;
    this.propLoading.set(true);
    this.api.enregistrerEvenementsLot(props).subscribe({
      next: () => { this.propositions.set(null); this.propLoading.set(false); this.load(); },
      error: err => { this.propError.set(err.error ? JSON.stringify(err.error) : `Erreur ${err.status}`); this.propLoading.set(false); },
    });
  }
}
