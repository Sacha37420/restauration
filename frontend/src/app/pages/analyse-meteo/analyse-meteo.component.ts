import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DecimalPipe } from '@angular/common';
import {
  ApiService, DonneeMeteoHoraire, IndicateurMeteoConfig, IndicateursJournaliers,
} from '../../core/api.service';

@Component({
  selector: 'app-analyse-meteo',
  standalone: true,
  imports: [FormsModule, DecimalPipe],
  templateUrl: './analyse-meteo.component.html',
  styleUrl: './analyse-meteo.component.scss',
})
export class AnalyseMeteoComponent implements OnInit {
  private api = inject(ApiService);

  ville = '';
  annee: number = new Date().getFullYear();
  mois: number | null = null;

  loading = signal(false);
  error = signal<string | null>(null);
  message = signal<string | null>(null);

  // Indicateurs journaliers calculés
  journalier = signal<IndicateursJournaliers | null>(null);

  // Détail horaire d'un jour
  jourSelectionne = signal<string | null>(null);
  heures = signal<DonneeMeteoHoraire[]>([]);
  editHeure = signal<DonneeMeteoHoraire | null>(null);

  // Configuration des indicateurs
  indicateurs = signal<IndicateurMeteoConfig[]>([]);
  editIndic = signal<IndicateurMeteoConfig | null>(null);

  champs = [
    { v: 'temperature', l: 'Température' },
    { v: 'nebulosite', l: 'Nébulosité' },
    { v: 'precipitation', l: 'Précipitation' },
  ];
  agregations = [
    { v: 'moyenne', l: 'Moyenne' }, { v: 'min', l: 'Minimum' }, { v: 'max', l: 'Maximum' },
    { v: 'somme', l: 'Somme' }, { v: 'amplitude', l: 'Amplitude' },
  ];

  ngOnInit(): void { this.loadIndicateurs(); }

  // ── Récupération + calcul ──
  recuperer(): void {
    if (!this.ville || !this.annee) { this.error.set('Renseigne une ville et une année.'); return; }
    this.loading.set(true); this.error.set(null); this.message.set(null);
    this.api.recupererMeteo({ ville: this.ville, mois: this.mois, annee: this.annee }).subscribe({
      next: r => { this.message.set(r.detail); this.loading.set(false); this.calculer(); },
      error: err => { this.error.set(err.error?.detail ?? `Erreur ${err.status}`); this.loading.set(false); },
    });
  }

  calculer(): void {
    if (!this.ville || !this.annee) { this.error.set('Renseigne une ville et une année.'); return; }
    this.loading.set(true); this.error.set(null);
    this.jourSelectionne.set(null);
    this.api.getIndicateursJournaliers({ ville: this.ville, annee: this.annee, mois: this.mois }).subscribe({
      next: j => { this.journalier.set(j); this.loading.set(false); },
      error: err => { this.error.set(err.error?.detail ?? `Erreur ${err.status}`); this.loading.set(false); },
    });
  }

  // ── Détail horaire d'un jour ──
  ouvrirJour(date: string): void {
    this.jourSelectionne.set(date);
    this.api.getMeteoHoraire({ ville: this.ville, date }).subscribe({
      next: h => this.heures.set(h),
    });
  }
  fermerJour(): void { this.jourSelectionne.set(null); this.heures.set([]); this.editHeure.set(null); }

  nouvelleHeure(): void {
    const jour = this.jourSelectionne();
    this.editHeure.set({
      ville: this.ville, horodatage: jour ? `${jour}T12:00:00Z` : '',
      temperature: null, nebulosite: null, precipitation: null, source: 'manuel',
    });
  }
  editerHeure(h: DonneeMeteoHoraire): void { this.editHeure.set({ ...h }); }
  enregistrerHeure(): void {
    const h = this.editHeure(); if (!h || !h.horodatage) return;
    const obs = h.id ? this.api.updateMeteoHoraire(h.id, h) : this.api.createMeteoHoraire(h);
    obs.subscribe({
      next: () => { this.editHeure.set(null); const j = this.jourSelectionne(); if (j) this.ouvrirJour(j); },
      error: err => this.error.set(err.error ? JSON.stringify(err.error) : `Erreur ${err.status}`),
    });
  }
  supprimerHeure(h: DonneeMeteoHoraire): void {
    if (!h.id) return;
    this.api.deleteMeteoHoraire(h.id).subscribe({ next: () => { const j = this.jourSelectionne(); if (j) this.ouvrirJour(j); } });
  }

  // ── Configuration indicateurs ──
  loadIndicateurs(): void {
    this.api.getIndicateursMeteo().subscribe({ next: i => this.indicateurs.set(i) });
  }
  nouvelIndicateur(): void {
    this.editIndic.set({ nom: '', champ: 'temperature', agregation: 'moyenne', heure_debut: 0, heure_fin: 23, actif: true });
  }
  editerIndicateur(i: IndicateurMeteoConfig): void { this.editIndic.set({ ...i }); }
  enregistrerIndicateur(): void {
    const i = this.editIndic(); if (!i || !i.nom) { this.error.set('Nom de l\'indicateur requis.'); return; }
    const obs = i.id ? this.api.updateIndicateurMeteo(i.id, i) : this.api.createIndicateurMeteo(i);
    obs.subscribe({
      next: () => { this.editIndic.set(null); this.loadIndicateurs(); if (this.journalier()) this.calculer(); },
      error: err => this.error.set(err.error ? JSON.stringify(err.error) : `Erreur ${err.status}`),
    });
  }
  supprimerIndicateur(i: IndicateurMeteoConfig): void {
    if (!i.id || !confirm(`Supprimer l'indicateur « ${i.nom} » ?`)) return;
    this.api.deleteIndicateurMeteo(i.id).subscribe({ next: () => { this.loadIndicateurs(); if (this.journalier()) this.calculer(); } });
  }
}
