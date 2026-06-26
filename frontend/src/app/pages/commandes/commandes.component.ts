import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe, DecimalPipe } from '@angular/common';
import {
  ApiService, Commande, Plat, CanalCommande, StatutCommande, StatutPaiement, Facture,
} from '../../core/api.service';

const METHODES_PAIEMENT = ['carte', 'espèces', 'ticket_restaurant', 'virement'];

@Component({
  selector: 'app-commandes',
  standalone: true,
  imports: [FormsModule, DatePipe, DecimalPipe],
  templateUrl: './commandes.component.html',
  styleUrl: './commandes.component.scss',
})
export class CommandesComponent implements OnInit {
  private api = inject(ApiService);

  items = signal<Commande[]>([]);
  plats = signal<Plat[]>([]);
  canaux = signal<CanalCommande[]>([]);
  statuts = signal<StatutCommande[]>([]);
  statutsPaiement = signal<StatutPaiement[]>([]);
  loading = signal(true);
  error = signal<string | null>(null);
  showCreateModal = signal(false);
  showDetail = signal(false);
  selectedCommande = signal<Commande | null>(null);

  // Filtres
  filterStatut = signal<number | ''>('');
  filterCanal = signal<number | ''>('');
  filterDateDebut = signal('');
  filterDateFin = signal('');

  createForm: { numero_table?: number | null; canal?: number } = {};
  createError = signal<string | null>(null);

  ligneForm = { plat: 0, quantite: 1 };

  paiementForm = { methode: 'espèces' };
  paiementError = signal<string | null>(null);
  methodesPaiement = METHODES_PAIEMENT;

  // Facture
  facture = signal<Facture | null>(null);
  factureEmail = '';
  factureLoading = signal(false);
  factureError = signal<string | null>(null);
  factureMessage = signal<string | null>(null);

  ngOnInit(): void {
    this.load();
    this.api.getPlats({ actif: true }).subscribe({ next: p => this.plats.set(p) });
    this.api.getCanaux().subscribe({ next: c => this.canaux.set(c) });
    this.api.getStatutsCommande().subscribe({ next: s => this.statuts.set(s) });
    this.api.getStatutsPaiement().subscribe({ next: s => this.statutsPaiement.set(s) });
  }

  load(): void {
    this.loading.set(true);
    const filters: Record<string, string | number> = {};
    if (this.filterStatut()) filters['statut'] = this.filterStatut() as number;
    if (this.filterCanal()) filters['canal'] = this.filterCanal() as number;
    if (this.filterDateDebut()) filters['date_debut'] = this.filterDateDebut();
    if (this.filterDateFin()) filters['date_fin'] = this.filterDateFin();
    this.api.getCommandes(filters as never).subscribe({
      next: items => { this.items.set(items); this.loading.set(false); },
      error: err => { this.error.set(`Erreur ${err.status}`); this.loading.set(false); },
    });
  }

  applyFilters(): void { this.load(); }

  resetFilters(): void {
    this.filterStatut.set('');
    this.filterCanal.set('');
    this.filterDateDebut.set('');
    this.filterDateFin.set('');
    this.load();
  }

  openCreate(): void {
    this.createForm = { numero_table: undefined, canal: this.canaux()[0]?.id };
    this.createError.set(null);
    this.showCreateModal.set(true);
  }

  create(): void {
    const firstStatut = this.statuts()[0];
    if (!firstStatut) {
      this.createError.set('Aucun statut disponible. Vérifiez la base de données.');
      return;
    }
    this.createError.set(null);
    this.api.createCommande({
      numero_table: this.createForm.numero_table ?? null,
      canal: this.createForm.canal,
      statut: firstStatut.id!,
    }).subscribe({
      next: c => {
        this.showCreateModal.set(false);
        this.load();
        this.openDetail(c);
      },
      error: err => {
        const msg = err.error ? JSON.stringify(err.error) : `Erreur ${err.status}`;
        this.createError.set(msg);
      },
    });
  }

  openDetail(c: Commande): void {
    this.api.getCommande(c.id!).subscribe({
      next: full => {
        this.selectedCommande.set(full);
        this.showDetail.set(true);
      },
    });
    this.ligneForm = { plat: 0, quantite: 1 };
    this.paiementError.set(null);
    // Facture (peut ne pas exister → 404 silencieux)
    this.facture.set(null);
    this.factureError.set(null);
    this.factureMessage.set(null);
    this.factureEmail = '';
    this.api.getFacture(c.id!).subscribe({
      next: f => { this.facture.set(f); this.factureEmail = f.email_destinataire ?? ''; },
      error: () => { /* pas encore de facture */ },
    });
  }

  addLigne(): void {
    const c = this.selectedCommande();
    if (!c?.id || !this.ligneForm.plat) return;
    this.api.addLigneCommande(c.id, {
      plat: +this.ligneForm.plat,
      quantite: this.ligneForm.quantite,
      prix_unitaire_snapshot: 0,
    }).subscribe({ next: () => this.openDetail(c) });
  }

  deleteLigne(ligneId: number): void {
    const c = this.selectedCommande();
    if (!c?.id) return;
    this.api.deleteLigneCommande(c.id, ligneId).subscribe({
      next: () => this.openDetail(c),
    });
  }

  updateStatut(c: Commande, statutId: number): void {
    this.api.updateCommande(c.id!, { statut: statutId }).subscribe({
      next: () => { this.load(); if (this.selectedCommande()?.id === c.id) this.openDetail(c); },
    });
  }

  // Encaissement sur place par l'employé connecté (liquide, ticket resto…).
  // Crée le paiement s'il n'existe pas, ou confirme un paiement « en attente ».
  confirmerSurPlace(): void {
    const c = this.selectedCommande();
    if (!c?.id) return;
    this.paiementError.set(null);
    this.api.confirmerPaiementSurPlace(c.id, this.paiementForm.methode).subscribe({
      next: () => this.openDetail(c),
      error: err => {
        const msg = err.error?.detail ?? (err.error ? JSON.stringify(err.error) : `Erreur ${err.status}`);
        this.paiementError.set(msg);
      },
    });
  }

  updateStatutPaiement(statutId: number): void {
    const c = this.selectedCommande();
    if (!c?.id || !c.paiement?.id) return;
    this.api.updatePaiement(c.paiement.id, { statut: statutId }).subscribe({
      next: () => this.openDetail(c),
    });
  }

  genererFacture(): void {
    const c = this.selectedCommande();
    if (!c?.id) return;
    this.factureLoading.set(true);
    this.factureError.set(null);
    this.factureMessage.set(null);
    this.api.genererFacture(c.id).subscribe({
      next: f => { this.facture.set(f); this.factureLoading.set(false); },
      error: err => {
        this.factureError.set(err.error?.detail ?? `Erreur ${err.status}`);
        this.factureLoading.set(false);
      },
    });
  }

  envoyerFactureEmail(): void {
    const c = this.selectedCommande();
    if (!c?.id || !this.factureEmail) return;
    this.factureLoading.set(true);
    this.factureError.set(null);
    this.factureMessage.set(null);
    this.api.genererFacture(c.id, this.factureEmail).subscribe({
      next: f => {
        this.facture.set(f);
        this.factureLoading.set(false);
        this.factureMessage.set(`Facture envoyée à ${this.factureEmail}.`);
      },
      error: err => {
        this.factureError.set(err.error?.detail ?? `Erreur ${err.status}`);
        this.factureLoading.set(false);
      },
    });
  }

  telechargerFacture(): void {
    const c = this.selectedCommande();
    if (!c?.id) return;
    this.api.telechargerFacturePdf(c.id).subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob);
        window.open(url, '_blank');
        setTimeout(() => URL.revokeObjectURL(url), 10000);
      },
      error: err => this.factureError.set(`Erreur ${err.status}`),
    });
  }

  statutName(id: number): string {
    return this.statuts().find(s => s.id === id)?.nom ?? String(id);
  }

  platName(id: number): string {
    return this.plats().find(p => p.id === id)?.nom ?? String(id);
  }

  total(c: Commande): number {
    return (c.lignes_commande ?? []).reduce(
      (s, l) => s + +l.quantite * +l.prix_unitaire_snapshot, 0
    );
  }

  close(): void { this.showCreateModal.set(false); this.showDetail.set(false); }
}
