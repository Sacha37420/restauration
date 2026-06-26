import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService, CategoriePlat, SousCategoriePlat } from '../../core/api.service';

@Component({
  selector: 'app-categories-plat',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './categories-plat.component.html',
  styleUrl: './categories-plat.component.scss',
})
export class CategoriesPlatComponent implements OnInit {
  private api = inject(ApiService);

  categories = signal<CategoriePlat[]>([]);
  sousCategories = signal<SousCategoriePlat[]>([]);
  loading = signal(true);
  error = signal<string | null>(null);

  showCatModal = signal(false);
  showScModal = signal(false);
  editingCat = signal<CategoriePlat | null>(null);
  editingSc = signal<SousCategoriePlat | null>(null);
  catForm: Partial<CategoriePlat> = {};
  scForm: Partial<SousCategoriePlat> = {};

  ngOnInit(): void { this.load(); }

  load(): void {
    this.loading.set(true);
    this.api.getCategories().subscribe({
      next: c => {
        this.categories.set(c);
        this.api.getSousCategories().subscribe({
          next: s => { this.sousCategories.set(s); this.loading.set(false); },
          error: () => { this.error.set('Erreur chargement sous-catégories.'); this.loading.set(false); },
        });
      },
      error: () => { this.error.set('Erreur chargement catégories.'); this.loading.set(false); },
    });
  }

  sousCategoriesDe(categorieId: number): SousCategoriePlat[] {
    return this.sousCategories().filter(sc => sc.categorie === categorieId);
  }

  // ── Catégories ────────────────────────────────────────────────────────
  openCreateCat(): void {
    this.catForm = { nom: '', ordre: this.categories().length * 10 };
    this.editingCat.set(null);
    this.showCatModal.set(true);
  }

  openEditCat(c: CategoriePlat): void {
    this.catForm = { ...c };
    this.editingCat.set(c);
    this.showCatModal.set(true);
  }

  saveCat(): void {
    const id = this.editingCat()?.id;
    const obs = id
      ? this.api.updateCategorie(id, this.catForm)
      : this.api.createCategorie(this.catForm);
    obs.subscribe({ next: () => { this.showCatModal.set(false); this.load(); } });
  }

  deleteCat(c: CategoriePlat): void {
    if (!confirm(`Supprimer la catégorie "${c.nom}" et toutes ses sous-catégories ?`)) return;
    this.api.deleteCategorie(c.id!).subscribe({ next: () => this.load() });
  }

  // ── Sous-catégories ───────────────────────────────────────────────────
  openCreateSc(categorieId: number): void {
    const existingSc = this.sousCategoriesDe(categorieId);
    this.scForm = { nom: '', ordre: existingSc.length * 10, categorie: categorieId };
    this.editingSc.set(null);
    this.showScModal.set(true);
  }

  openEditSc(sc: SousCategoriePlat): void {
    this.scForm = { ...sc };
    this.editingSc.set(sc);
    this.showScModal.set(true);
  }

  saveSc(): void {
    const id = this.editingSc()?.id;
    const obs = id
      ? this.api.updateSousCategorie(id, this.scForm)
      : this.api.createSousCategorie(this.scForm);
    obs.subscribe({ next: () => { this.showScModal.set(false); this.load(); } });
  }

  deleteSc(sc: SousCategoriePlat): void {
    if (!confirm(`Supprimer la sous-catégorie "${sc.nom}" ?`)) return;
    this.api.deleteSousCategorie(sc.id!).subscribe({ next: () => this.load() });
  }

  closeCat(): void { this.showCatModal.set(false); }
  closeSc(): void { this.showScModal.set(false); }
}
