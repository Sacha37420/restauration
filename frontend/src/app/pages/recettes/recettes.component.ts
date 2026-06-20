import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, Recette, LigneRecette, Ingredient } from '../../core/api.service';

@Component({
  selector: 'app-recettes',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './recettes.component.html',
  styleUrl: './recettes.component.scss',
})
export class RecettesComponent implements OnInit {
  private api = inject(ApiService);

  items = signal<Recette[]>([]);
  ingredients = signal<Ingredient[]>([]);
  loading = signal(true);
  error = signal<string | null>(null);
  showModal = signal(false);
  showDetail = signal(false);
  editing = signal<Recette | null>(null);
  detail = signal<Recette | null>(null);

  form: Partial<Recette> = {};
  ligneForm: Partial<LigneRecette> = { quantite: 1 };

  ngOnInit(): void {
    this.load();
    this.api.getIngredients().subscribe({ next: i => this.ingredients.set(i) });
  }

  load(): void {
    this.loading.set(true);
    this.api.getRecettes().subscribe({
      next: items => { this.items.set(items); this.loading.set(false); },
      error: err => { this.error.set(`Erreur ${err.status}`); this.loading.set(false); },
    });
  }

  openCreate(): void {
    this.form = { nom: '', instructions_html: '', temps_preparation: 0, nb_portions: 1 };
    this.editing.set(null);
    this.showModal.set(true);
  }

  openEdit(item: Recette): void {
    this.form = { ...item };
    this.editing.set(item);
    this.showModal.set(true);
  }

  openDetail(item: Recette): void {
    this.api.getRecette(item.id!).subscribe({
      next: r => { this.detail.set(r); this.showDetail.set(true); },
    });
    this.ligneForm = { quantite: 1 };
  }

  save(): void {
    const id = this.editing()?.id;
    const obs = id
      ? this.api.updateRecette(id, this.form)
      : this.api.createRecette(this.form);
    obs.subscribe({ next: () => { this.showModal.set(false); this.load(); } });
  }

  addLigne(): void {
    const id = this.detail()?.id;
    if (!id || !this.ligneForm.ingredient || !this.ligneForm.quantite) return;
    this.api.addLigneRecette(id, this.ligneForm as LigneRecette).subscribe({
      next: () => this.openDetail(this.detail()!),
    });
  }

  deleteLigne(ligneId: number): void {
    const id = this.detail()?.id;
    if (!id) return;
    this.api.deleteLigneRecette(id, ligneId).subscribe({
      next: () => this.openDetail(this.detail()!),
    });
  }

  delete(item: Recette): void {
    if (!confirm(`Supprimer "${item.nom}" ?`)) return;
    this.api.deleteRecette(item.id!).subscribe({ next: () => this.load() });
  }

  ingredientName(id: number): string {
    return this.ingredients().find(i => i.id === id)?.nom ?? String(id);
  }

  close(): void { this.showModal.set(false); this.showDetail.set(false); }
}
