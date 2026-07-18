import {
  Component, inject, OnInit, signal, computed,
  ViewChild, ElementRef, HostListener,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe, DecimalPipe } from '@angular/common';
import { ApiService, TableRestaurant, Commande, StatutCommande } from '../../core/api.service';
import * as QRCode from 'qrcode';

// Ordre de priorité d'affichage (plus le chiffre est bas, plus c'est urgent)
const STATUT_PRIORITY: Record<string, number> = {
  prete: 0,
  en_attente: 1,
  en_preparation: 2,
  servie: 3,
  annulee: 4,
};

// Couleurs sémantiques Foyer (cf. styles.scss) : en_attente → warning,
// en_preparation → accent, prete → success, servie → neutre (terminé, ne
// requiert plus d'action), annulee → danger.
const STATUT_COLOR: Record<string, string> = {
  prete:          'var(--success)',
  en_attente:     'var(--warning)',
  en_preparation: 'var(--accent)',
  servie:         'var(--text-mute)',
  annulee:        'var(--danger)',
};

const STATUT_LABEL: Record<string, string> = {
  prete:          'Prête',
  en_attente:     'En attente',
  en_preparation: 'En préparation',
  servie:         'Servie',
  annulee:        'Annulée',
};

@Component({
  selector: 'app-plan-tables',
  standalone: true,
  imports: [FormsModule, DatePipe, DecimalPipe],
  templateUrl: './plan-tables.component.html',
  styleUrl: './plan-tables.component.scss',
})
export class PlanTablesComponent implements OnInit {
  @ViewChild('planContainer') planContainer!: ElementRef<HTMLDivElement>;

  private api = inject(ApiService);

  tables = signal<TableRestaurant[]>([]);
  statuts = signal<StatutCommande[]>([]);
  commandesAujourdhui = signal<Commande[]>([]);
  selectedTable = signal<TableRestaurant | null>(null);
  selectedTableCommandes = signal<Commande[]>([]);
  editMode = signal(false);
  loading = signal(true);
  error = signal<string | null>(null);

  // Formulaire ajout table
  showAddForm = signal(false);
  addForm = { numero: 1 };
  addError = signal<string | null>(null);

  // Drag state
  private dragState: {
    tableId: number;
    startMouseX: number;
    startMouseY: number;
    origX: number;
    origY: number;
  } | null = null;
  isDragging = signal(false);

  // Map numero_table → commandes du jour
  commandesByTable = computed(() => {
    const map = new Map<number, Commande[]>();
    for (const c of this.commandesAujourdhui()) {
      if (c.numero_table == null) continue;
      const list = map.get(c.numero_table) ?? [];
      list.push(c);
      map.set(c.numero_table, list);
    }
    return map;
  });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    const today = new Date().toISOString().split('T')[0];

    this.api.getTables().subscribe({ next: t => this.tables.set(this.autoLayout(t)) });
    this.api.getStatutsCommande().subscribe({ next: s => this.statuts.set(s) });
    this.api.getCommandes({ date_debut: today, date_fin: today }).subscribe({
      next: c => { this.commandesAujourdhui.set(c); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  // Positionne automatiquement les tables sans position définie
  private autoLayout(tables: TableRestaurant[]): TableRestaurant[] {
    const cols = 5;
    const cellW = 18;
    const cellH = 25;
    let idx = 0;
    return tables.map(t => {
      if (t.pos_x != null && t.pos_y != null) return t;
      const col = idx % cols;
      const row = Math.floor(idx / cols);
      idx++;
      return { ...t, pos_x: 5 + col * cellW, pos_y: 8 + row * cellH };
    });
  }

  // ── Drag & Drop ──────────────────────────────────────────────

  startDrag(event: MouseEvent, table: TableRestaurant): void {
    if (!this.editMode()) return;
    event.preventDefault();
    event.stopPropagation();
    this.dragState = {
      tableId: table.id!,
      startMouseX: event.clientX,
      startMouseY: event.clientY,
      origX: table.pos_x ?? 10,
      origY: table.pos_y ?? 10,
    };
    this.isDragging.set(true);
  }

  @HostListener('document:mousemove', ['$event'])
  onMouseMove(event: MouseEvent): void {
    if (!this.dragState || !this.planContainer) return;
    const rect = this.planContainer.nativeElement.getBoundingClientRect();
    const dx = ((event.clientX - this.dragState.startMouseX) / rect.width) * 100;
    const dy = ((event.clientY - this.dragState.startMouseY) / rect.height) * 100;
    const newX = Math.max(1, Math.min(88, this.dragState.origX + dx));
    const newY = Math.max(1, Math.min(88, this.dragState.origY + dy));
    this.tables.update(ts =>
      ts.map(t => t.id === this.dragState!.tableId ? { ...t, pos_x: newX, pos_y: newY } : t)
    );
  }

  @HostListener('document:mouseup')
  onMouseUp(): void {
    if (!this.dragState) return;
    const moved = this.tables().find(t => t.id === this.dragState!.tableId);
    if (moved) this.savePosition(moved);
    this.dragState = null;
    this.isDragging.set(false);
  }

  private savePosition(table: TableRestaurant): void {
    this.api.updateTable(table.id!, {
      numero: table.numero,
      token_qr: table.token_qr,
      actif: table.actif,
      pos_x: table.pos_x,
      pos_y: table.pos_y,
    }).subscribe();
  }

  // ── Sélection table ──────────────────────────────────────────

  selectTable(table: TableRestaurant): void {
    if (this.isDragging()) return;
    if (this.selectedTable()?.id === table.id) {
      this.selectedTable.set(null);
      this.selectedTableCommandes.set([]);
      return;
    }
    this.selectedTable.set(table);
    const today = new Date().toISOString().split('T')[0];
    this.api.getCommandes({ numero_table: table.numero, date_debut: today, date_fin: today, limit: 10 }).subscribe({
      next: c => this.selectedTableCommandes.set(c),
    });
  }

  // ── Couleur table (basée sur statut le plus urgent) ──────────

  tableColor(table: TableRestaurant): string {
    const commandes = this.commandesByTable().get(table.numero) ?? [];
    const active = commandes.filter(c => {
      const nom = this.statutNom(c.statut);
      return nom !== 'servie' && nom !== 'annulee';
    });
    if (active.length === 0) {
      return commandes.length > 0 ? STATUT_COLOR['servie'] : 'var(--border)';
    }
    const best = active.reduce((prev, curr) => {
      const pPrev = STATUT_PRIORITY[this.statutNom(prev.statut)] ?? 99;
      const pCurr = STATUT_PRIORITY[this.statutNom(curr.statut)] ?? 99;
      return pCurr < pPrev ? curr : prev;
    });
    return STATUT_COLOR[this.statutNom(best.statut)] ?? 'var(--border)';
  }

  tableBadgeCount(table: TableRestaurant): number {
    return (this.commandesByTable().get(table.numero) ?? [])
      .filter(c => {
        const nom = this.statutNom(c.statut);
        return nom !== 'servie' && nom !== 'annulee';
      }).length;
  }

  statutNom(id: number): string {
    return this.statuts().find(s => s.id === id)?.nom ?? '';
  }

  statutLabel(id: number): string {
    return STATUT_LABEL[this.statutNom(id)] ?? this.statutNom(id);
  }

  statutColor(id: number): string {
    return STATUT_COLOR[this.statutNom(id)] ?? 'var(--border)';
  }

  commandeTotal(c: Commande): number {
    return (c.lignes_commande ?? []).reduce((s, l) => s + +l.quantite * +l.prix_unitaire_snapshot, 0);
  }

  // ── Ajout / suppression de table ─────────────────────────────

  openAddForm(): void {
    const maxNumero = Math.max(0, ...this.tables().map(t => t.numero));
    this.addForm.numero = maxNumero + 1;
    this.addError.set(null);
    this.showAddForm.set(true);
  }

  addTable(): void {
    this.addError.set(null);
    const token = Array.from(crypto.getRandomValues(new Uint8Array(20)))
      .map(b => b.toString(16).padStart(2, '0'))
      .join('');
    this.api.createTable({
      numero: this.addForm.numero,
      token_qr: token,
      actif: true,
      pos_x: 45,
      pos_y: 45,
    }).subscribe({
      next: t => {
        this.tables.update(ts => [...ts, t]);
        this.showAddForm.set(false);
      },
      error: err => {
        const msg = err.error ? JSON.stringify(err.error) : `Erreur ${err.status}`;
        this.addError.set(msg);
      },
    });
  }

  deleteTable(table: TableRestaurant, event: MouseEvent): void {
    event.stopPropagation();
    if (!confirm(`Supprimer la table ${table.numero} ?`)) return;
    this.api.deleteTable(table.id!).subscribe({
      next: () => {
        this.tables.update(ts => ts.filter(t => t.id !== table.id));
        if (this.selectedTable()?.id === table.id) this.selectedTable.set(null);
      },
    });
  }

  toggleActive(table: TableRestaurant, event: MouseEvent): void {
    event.stopPropagation();
    this.api.updateTable(table.id!, { ...table, actif: !table.actif }).subscribe({
      next: updated => this.tables.update(ts => ts.map(t => t.id === updated.id ? updated : t)),
    });
  }

  // ── Export QR codes ──────────────────────────────────────────

  // Tables sélectionnées pour l'export (null = toutes les actives)
  exportSelection = signal<Set<number>>(new Set());
  showExportModal = signal(false);

  openExportModal(): void {
    this.selectAllTables();
    this.showExportModal.set(true);
  }

  selectAllTables(): void {
    this.exportSelection.set(new Set(this.tables().filter(t => t.actif).map(t => t.id!)));
  }

  deselectAllTables(): void {
    this.exportSelection.set(new Set());
  }

  toggleExportTable(id: number): void {
    this.exportSelection.update(s => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  isExportSelected(id: number): boolean {
    return this.exportSelection().has(id);
  }

  /** URL absolue vers /commander pour une table donnée, tenant compte du base href. */
  commanderUrl(tableNum: number): string {
    const base = document.querySelector('base')?.getAttribute('href') ?? '/';
    const appRoot = window.location.origin + base.replace(/\/$/, '');
    return `${appRoot}/commander?table=${tableNum}`;
  }

  async exportQRCodes(): Promise<void> {
    const selected = this.tables().filter(t => this.exportSelection().has(t.id!));
    if (selected.length === 0) return;

    // La fenêtre doit être ouverte de façon synchrone, dans le geste utilisateur :
    // après un `await`, le bloqueur de popups l'empêcherait.
    const printWindow = window.open('', '_blank');
    if (!printWindow) {
      alert('Le navigateur a bloqué l\'ouverture de la fenêtre. Autorisez les popups pour ce site.');
      return;
    }
    printWindow.document.write(
      '<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8">' +
      '<title>QR Codes — Tables du restaurant</title></head>' +
      '<body style="font-family:sans-serif;color:#555;padding:2rem">Génération des QR codes…</body></html>');
    printWindow.document.close();

    const base = document.querySelector('base')?.getAttribute('href') ?? '/';
    const baseUrl = window.location.origin + base.replace(/\/$/, '');

    try {
      // QR générés localement via la librairie embarquée (aucune dépendance CDN).
      const cards = await Promise.all(selected.map(async t => ({
        numero: t.numero,
        dataUrl: await QRCode.toDataURL(`${baseUrl}/commander?table=${t.numero}`, {
          width: 260, margin: 1, color: { dark: '#1a237e', light: '#ffffff' },
        }),
      })));
      printWindow.document.open();
      printWindow.document.write(this.buildPrintHtml(cards, baseUrl));
      printWindow.document.close();
      this.showExportModal.set(false);
    } catch (e) {
      printWindow.document.body.innerHTML =
        '<p style="color:red;padding:2rem">Erreur lors de la génération des QR codes : ' +
        (e as Error).message + '</p>';
    }
  }

  private buildPrintHtml(cards: { numero: number; dataUrl: string }[], baseUrl: string): string {
    const cardsHtml = cards.map(c => `
      <div class="qr-card">
        <div class="cut-corner"></div>
        <img class="qr-canvas" src="${c.dataUrl}" alt="QR table ${c.numero}" width="260" height="260">
        <div class="table-label">Table ${c.numero}</div>
        <div class="table-url">${baseUrl}/commander?table=${c.numero}</div>
      </div>`).join('');

    return `<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>QR Codes — Tables du restaurant</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; }

    @page {
      size: A4 portrait;
      margin: 12mm;
    }

    body {
      margin: 0;
      padding: 0;
      font-family: 'Segoe UI', Arial, sans-serif;
      background: #fff;
      color: #111;
    }

    .page-title {
      text-align: center;
      font-size: 11pt;
      color: #999;
      margin-bottom: 6mm;
      letter-spacing: 0.05em;
    }

    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6mm;
    }

    .qr-card {
      border: 1.5px dashed #c0c8e0;
      border-radius: 6px;
      padding: 7mm 5mm 5mm;
      text-align: center;
      page-break-inside: avoid;
      break-inside: avoid;
      position: relative;
      background: #fff;
    }

    /* Petit repère de découpe aux coins */
    .qr-card::before, .qr-card::after {
      content: '';
      position: absolute;
      width: 6px;
      height: 6px;
      border-color: #aaa;
      border-style: solid;
    }
    .qr-card::before { top: 3px; left: 3px; border-width: 1.5px 0 0 1.5px; }
    .qr-card::after  { bottom: 3px; right: 3px; border-width: 0 1.5px 1.5px 0; }

    .qr-canvas {
      display: block;
      margin: 0 auto 4mm;
      border-radius: 4px;
    }

    .table-label {
      font-size: 28pt;
      font-weight: 800;
      color: #1a237e;
      letter-spacing: -0.02em;
      line-height: 1;
      margin-bottom: 2mm;
    }

    .table-url {
      font-size: 6.5pt;
      color: #999;
      word-break: break-all;
      margin-top: 2mm;
    }

    @media print {
      body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    }
  </style>
</head>
<body>
  <div class="page-title">QR Codes — Commandes en ligne</div>
  <div class="grid">${cardsHtml}</div>
  <script>
    window.onload = function() { setTimeout(function() { window.print(); }, 300); };
  <\/script>
</body>
</html>`;
  }
}
