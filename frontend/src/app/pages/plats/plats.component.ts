import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DecimalPipe } from '@angular/common';
import { ApiService, Plat, Recette, CategoriePlat, SousCategoriePlat } from '../../core/api.service';

@Component({
  selector: 'app-plats',
  standalone: true,
  imports: [FormsModule, DecimalPipe],
  templateUrl: './plats.component.html',
  styleUrl: './plats.component.scss',
})
export class PlatsComponent implements OnInit {
  private api = inject(ApiService);

  items = signal<Plat[]>([]);
  recettes = signal<Recette[]>([]);
  categories = signal<CategoriePlat[]>([]);
  sousCategories = signal<SousCategoriePlat[]>([]);
  loading = signal(true);
  error = signal<string | null>(null);
  showModal = signal(false);
  editing = signal<Plat | null>(null);

  filters = { actif: true as boolean | undefined, sans_gluten: undefined as boolean | undefined,
               halal: undefined as boolean | undefined, vegetarien: undefined as boolean | undefined };
  form: Partial<Plat> = {};

  ngOnInit(): void {
    this.load();
    this.api.getRecettes().subscribe({ next: r => this.recettes.set(r) });
    this.api.getCategories().subscribe({ next: c => this.categories.set(c) });
    this.api.getSousCategories().subscribe({ next: s => this.sousCategories.set(s) });
  }

  selectedCategorieId: number | null = null;

  sousCategoriesFiltrees(): SousCategoriePlat[] {
    if (!this.selectedCategorieId) return [];
    return this.sousCategories().filter(sc => sc.categorie === this.selectedCategorieId);
  }

  onCategorieChange(): void {
    this.form.sous_categorie = null;
  }

  load(): void {
    this.loading.set(true);
    const f: Record<string, boolean> = {};
    if (this.filters.actif !== undefined) f['actif'] = this.filters.actif;
    if (this.filters.sans_gluten) f['sans_gluten'] = true;
    if (this.filters.halal) f['halal'] = true;
    if (this.filters.vegetarien) f['vegetarien'] = true;
    this.api.getPlats(f).subscribe({
      next: items => { this.items.set(items); this.loading.set(false); },
      error: err => { this.error.set(`Erreur ${err.status}`); this.loading.set(false); },
    });
  }

  openCreate(): void {
    this.form = { nom: '', description: '', prix_unitaire: 0,
                  sans_gluten: false, halal: false, vegetarien: false, actif: true,
                  recette: null, sous_categorie: null };
    this.selectedCategorieId = null;
    this.editing.set(null);
    this.showModal.set(true);
  }

  openEdit(item: Plat): void {
    this.form = { ...item };
    this.selectedCategorieId = item.sous_categorie_detail?.categorie_detail?.id ?? null;
    this.editing.set(item);
    this.showModal.set(true);
  }

  save(): void {
    const id = this.editing()?.id;
    const obs = id
      ? this.api.updatePlat(id, this.form)
      : this.api.createPlat(this.form);
    obs.subscribe({ next: () => { this.showModal.set(false); this.load(); } });
  }

  toggleActif(item: Plat): void {
    this.api.updatePlat(item.id!, { actif: !item.actif }).subscribe({ next: () => this.load() });
  }

  delete(item: Plat): void {
    if (!confirm(`Supprimer "${item.nom}" ?`)) return;
    this.api.deletePlat(item.id!).subscribe({ next: () => this.load() });
  }

  close(): void { this.showModal.set(false); }
}
