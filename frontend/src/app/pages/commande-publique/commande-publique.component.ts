import { Component, inject, OnInit, signal, computed } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { DecimalPipe } from '@angular/common';
import { ApiService, Plat, Commande, Paiement, CategoriePlat } from '../../core/api.service';
import { forkJoin } from 'rxjs';

type Etape = 'menu' | 'panier' | 'commande' | 'paiement' | 'recu' | 'stripe-attente';

const METHODES_PLACE = ['espèces', 'ticket_restaurant'];

interface CartItem {
  plat: Plat;
  quantite: number;
}

@Component({
  selector: 'app-commande-publique',
  standalone: true,
  imports: [FormsModule, DecimalPipe],
  templateUrl: './commande-publique.component.html',
  styleUrl: './commande-publique.component.scss',
})
export class CommandePubliqueComponent implements OnInit {
  private api = inject(ApiService);
  private route = inject(ActivatedRoute);

  tableId = signal(0);
  etape = signal<Etape>('menu');
  plats = signal<Plat[]>([]);
  cart = signal<CartItem[]>([]);
  commande = signal<Commande | null>(null);
  paiement = signal<Paiement | null>(null);
  loading = signal(false);
  error = signal<string | null>(null);
  stripeIndisponible = signal(false);
  categorieActive = signal<number | null>(null);

  methodePaiement = 'espèces';
  methodesPlace = METHODES_PLACE;

  // Groupement du menu par catégorie / sous-catégorie
  menuGroupe = computed(() => {
    const plats = this.plats();
    const groupes: Array<{
      categorie: { id: number; nom: string } | null;
      sousCats: Array<{
        id: number | null; nom: string | null;
        plats: Plat[];
      }>;
    }> = [];

    const catMap = new Map<number | null, Map<number | null, Plat[]>>();

    for (const p of plats) {
      const catId = p.sous_categorie_detail?.categorie_detail?.id ?? null;
      const scId  = p.sous_categorie_detail?.id ?? null;
      if (!catMap.has(catId)) catMap.set(catId, new Map());
      const scMap = catMap.get(catId)!;
      if (!scMap.has(scId)) scMap.set(scId, []);
      scMap.get(scId)!.push(p);
    }

    // Catégories triées (nulls en dernier)
    const catIds = [...catMap.keys()].sort((a, b) => {
      if (a === null) return 1; if (b === null) return -1;
      const pa = plats.find(p => p.sous_categorie_detail?.categorie_detail?.id === a);
      const pb = plats.find(p => p.sous_categorie_detail?.categorie_detail?.id === b);
      return (pa?.sous_categorie_detail?.categorie_detail as any)?.ordre - (pb?.sous_categorie_detail?.categorie_detail as any)?.ordre;
    });

    for (const catId of catIds) {
      const scMap = catMap.get(catId)!;
      const sample = [...scMap.values()][0]?.[0];
      const catObj = catId !== null ? { id: catId, nom: sample?.sous_categorie_detail?.categorie_detail?.nom ?? '' } : null;
      const sousCats: any[] = [];
      for (const [scId, platList] of scMap) {
        sousCats.push({
          id: scId,
          nom: scId !== null ? platList[0].sous_categorie_detail?.nom ?? null : null,
          plats: platList,
        });
      }
      sousCats.sort((a, b) => {
        if (a.id === null) return 1; if (b.id === null) return -1;
        return (a.plats[0].sous_categorie_detail?.ordre ?? 0) - (b.plats[0].sous_categorie_detail?.ordre ?? 0);
      });
      groupes.push({ categorie: catObj, sousCats });
    }

    return groupes;
  });

  categoriesMenu = computed(() =>
    this.menuGroupe().map(g => g.categorie)
  );

  platsVisibles = computed(() => {
    const actif = this.categorieActive();
    if (actif === null) return this.menuGroupe();
    return this.menuGroupe().filter(g => g.categorie?.id === actif || (actif === -1 && g.categorie === null));
  });

  cartTotal = computed(() =>
    this.cart().reduce((s, i) => s + +i.plat.prix_unitaire * i.quantite, 0)
  );
  cartCount = computed(() =>
    this.cart().reduce((s, i) => s + i.quantite, 0)
  );
  // Total depuis les lignes de commande (fiable même après retour Stripe, panier vide)
  commandeTotal = computed(() => {
    const lignes = this.commande()?.lignes_commande;
    if (lignes?.length) {
      return lignes.reduce((s, l) => s + l.quantite * +l.prix_unitaire_snapshot, 0);
    }
    return this.cartTotal();
  });

  ngOnInit(): void {
    const params = this.route.snapshot.queryParamMap;
    const paiementStatut = params.get('paiement');
    const commandeId = Number(params.get('commande') ?? 0);
    const table = Number(params.get('table') ?? 0);

    // Retour depuis Stripe
    if (paiementStatut && commandeId) {
      this.tableId.set(table);
      if (paiementStatut === 'succes') {
        this.chargerCommandeApresStripe(commandeId);
      } else {
        this.error.set('Paiement annulé. Vous pouvez réessayer.');
        this.chargerCommandeEtReprendreAuPaiement(commandeId);
      }
      return;
    }

    this.tableId.set(Number(params.get('table') ?? 0));
    this.loading.set(true);
    this.api.publicGetPlats().subscribe({
      next: p => { this.plats.set(p); this.loading.set(false); },
      error: () => { this.error.set('Impossible de charger la carte.'); this.loading.set(false); },
    });
  }

  private chargerCommandeApresStripe(commandeId: number): void {
    this.loading.set(true);
    this.etape.set('stripe-attente');
    this.api.publicGetCommande(commandeId).subscribe({
      next: cmd => {
        this.commande.set(cmd);
        this.loading.set(false);
        // Le webhook peut avoir un léger délai — on affiche le reçu dans tous les cas
        this.etape.set('recu');
      },
      error: () => {
        this.error.set('Impossible de récupérer votre commande.');
        this.loading.set(false);
        this.etape.set('menu');
      },
    });
  }

  private chargerCommandeEtReprendreAuPaiement(commandeId: number): void {
    this.loading.set(true);
    this.api.publicGetCommande(commandeId).subscribe({
      next: cmd => {
        this.commande.set(cmd);
        this.loading.set(false);
        this.etape.set('paiement');
      },
      error: () => {
        this.loading.set(false);
        this.etape.set('menu');
      },
    });
  }

  addToCart(plat: Plat): void {
    this.cart.update(items => {
      const existing = items.find(i => i.plat.id === plat.id);
      if (existing) {
        return items.map(i => i.plat.id === plat.id ? { ...i, quantite: i.quantite + 1 } : i);
      }
      return [...items, { plat, quantite: 1 }];
    });
  }

  increment(item: CartItem): void {
    this.cart.update(items =>
      items.map(i => i.plat.id === item.plat.id ? { ...i, quantite: i.quantite + 1 } : i)
    );
  }

  decrement(item: CartItem): void {
    this.cart.update(items => {
      const updated = items.map(i =>
        i.plat.id === item.plat.id ? { ...i, quantite: i.quantite - 1 } : i
      );
      return updated.filter(i => i.quantite > 0);
    });
  }

  removeItem(item: CartItem): void {
    this.cart.update(items => items.filter(i => i.plat.id !== item.plat.id));
  }

  quantiteInCart(plat: Plat): number {
    return this.cart().find(i => i.plat.id === plat.id)?.quantite ?? 0;
  }

  goToCart(): void { this.etape.set('panier'); }
  goToMenu(): void { this.etape.set('menu'); }

  submitOrder(): void {
    if (!this.tableId()) {
      this.error.set('Numéro de table manquant dans l\'URL (?table=X).');
      return;
    }
    if (this.cart().length === 0) return;

    this.loading.set(true);
    this.error.set(null);

    this.api.publicCreateCommande(this.tableId()).subscribe({
      next: (cmd) => {
        const lignes$ = this.cart().map(item =>
          this.api.publicAddLigne(cmd.id!, item.plat.id!, item.quantite)
        );
        forkJoin(lignes$).subscribe({
          next: () => {
            this.api.publicGetCommande(cmd.id!).subscribe({
              next: full => {
                this.commande.set(full);
                this.loading.set(false);
                this.etape.set('commande');
              },
            });
          },
          error: () => { this.error.set('Erreur lors de l\'envoi des plats.'); this.loading.set(false); },
        });
      },
      error: () => { this.error.set('Erreur lors de la création de la commande.'); this.loading.set(false); },
    });
  }

  goToPaiement(): void { this.etape.set('paiement'); }

  payerEnLigne(): void {
    const cmd = this.commande();
    if (!cmd?.id) return;
    this.loading.set(true);
    this.error.set(null);

    this.api.publicStripeCheckout(cmd.id).subscribe({
      next: res => {
        window.location.href = res.checkout_url;
      },
      error: err => {
        const msg = err.error?.detail ?? `Erreur ${err.status}`;
        if (err.status === 503) {
          this.stripeIndisponible.set(true);
        }
        this.error.set(msg);
        this.loading.set(false);
      },
    });
  }

  pay(): void {
    const cmd = this.commande();
    if (!cmd?.id) return;
    this.loading.set(true);
    this.error.set(null);

    this.api.publicPayer(cmd.id, this.methodePaiement).subscribe({
      next: p => {
        this.paiement.set(p);
        // Recharge la commande pour afficher le paiement avec son statut réel
        // (« en attente » = à encaisser sur place, non « payé »).
        this.api.publicGetCommande(cmd.id!).subscribe({
          next: full => { this.commande.set(full); this.loading.set(false); this.etape.set('recu'); },
          error: () => { this.loading.set(false); this.etape.set('recu'); },
        });
      },
      error: err => {
        const msg = err.error?.detail ?? `Erreur ${err.status}`;
        this.error.set(msg);
        this.loading.set(false);
      },
    });
  }
}
