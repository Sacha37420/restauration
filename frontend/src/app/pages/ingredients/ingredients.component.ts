import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, Ingredient, Fournisseur, Unite } from '../../core/api.service';

@Component({
  selector: 'app-ingredients',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './ingredients.component.html',
  styleUrl: './ingredients.component.scss',
})
export class IngredientsComponent implements OnInit {
  private api = inject(ApiService);

  items = signal<Ingredient[]>([]);
  fournisseurs = signal<Fournisseur[]>([]);
  unites = signal<Unite[]>([]);
  loading = signal(true);
  error = signal<string | null>(null);
  showModal = signal(false);
  showMouvModal = signal(false);
  editing = signal<Ingredient | null>(null);
  selectedIngredient = signal<Ingredient | null>(null);
  filterAlertes = signal(false);

  form: Partial<Ingredient> = {};
  mouvForm = { type: 'entree', quantite: 0, raison: '' };

  ngOnInit(): void {
    this.load();
    this.api.getFournisseurs().subscribe({
      next: f => this.fournisseurs.set(f),
      error: err => this.error.set(`Erreur chargement fournisseurs : ${err.status}`),
    });
    this.api.getUnites().subscribe({
      next: u => this.unites.set(u),
      error: err => this.error.set(`Erreur chargement unités : ${err.status}`),
    });
  }

  load(): void {
    this.loading.set(true);
    this.api.getIngredients(this.filterAlertes()).subscribe({
      next: items => { this.items.set(items); this.loading.set(false); },
      error: err => { this.error.set(`Erreur ${err.status}`); this.loading.set(false); },
    });
  }

  toggleAlertes(): void {
    this.filterAlertes.update(v => !v);
    this.load();
  }

  openCreate(): void {
    this.form = { nom: '', quantite_stock: 0, seuil_alerte: null, fournisseur: null, unite: undefined as unknown as number };
    this.editing.set(null);
    this.showModal.set(true);
  }

  openEdit(item: Ingredient): void {
    this.form = { ...item };
    this.editing.set(item);
    this.showModal.set(true);
  }

  openMouvement(item: Ingredient): void {
    this.selectedIngredient.set(item);
    this.mouvForm = { type: 'entree', quantite: 0, raison: '' };
    this.showMouvModal.set(true);
  }

  save(): void {
    const id = this.editing()?.id;
    const obs = id
      ? this.api.updateIngredient(id, this.form)
      : this.api.createIngredient(this.form);
    obs.subscribe({ next: () => { this.showModal.set(false); this.load(); } });
  }

  saveMouvement(): void {
    const ing = this.selectedIngredient();
    if (!ing?.id) return;
    this.api.createMouvementStock({
      ingredient: ing.id,
      ...this.mouvForm,
    }).subscribe({ next: () => { this.showMouvModal.set(false); this.load(); } });
  }

  delete(item: Ingredient): void {
    if (!confirm(`Supprimer "${item.nom}" ?`)) return;
    this.api.deleteIngredient(item.id!).subscribe({ next: () => this.load() });
  }

  close(): void { this.showModal.set(false); this.showMouvModal.set(false); }
}
