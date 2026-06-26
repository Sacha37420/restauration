import { Component, inject, OnInit, signal, computed } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { DecimalPipe } from '@angular/common';
import { ApiService, Plat, Commande, Paiement } from '../../core/api.service';
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

  methodePaiement = 'espèces';
  methodesPlace = METHODES_PLACE;

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
        this.loading.set(false);
        this.etape.set('recu');
      },
      error: err => {
        const msg = err.error?.detail ?? `Erreur ${err.status}`;
        this.error.set(msg);
        this.loading.set(false);
      },
    });
  }
}
