import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  ApiService, Recette, LigneRecette, Ingredient, RecetteProposee, SousCategoriePlat,
} from '../../core/api.service';

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

  // Génération Mistral : on propose, l'utilisateur valide, puis on enregistre.
  showGenModal = signal(false);
  showApercu = signal(false);
  generation = signal(false);
  proposee = signal<RecetteProposee | null>(null);
  sousCategories = signal<SousCategoriePlat[]>([]);

  form: Partial<Recette> = {};
  ligneForm: Partial<LigneRecette> = { quantite: 1 };

  genForm = { demande: '', nb_portions: 4, vegetarien: false, sans_gluten: false, halal: false };
  platForm = {
    creer: true, nom: '', description: '', prix_unitaire: 0,
    sous_categorie: null as number | null,
  };

  ngOnInit(): void {
    this.load();
    this.api.getIngredients().subscribe({ next: i => this.ingredients.set(i) });
    this.api.getSousCategories().subscribe({ next: s => this.sousCategories.set(s) });
  }

  // ----- Génération -----

  openGenerer(): void {
    this.genForm = { demande: '', nb_portions: 4, vegetarien: false, sans_gluten: false, halal: false };
    this.proposee.set(null);
    this.error.set(null);
    this.showGenModal.set(true);
  }

  private contraintes(): string[] {
    const c: string[] = [];
    if (this.genForm.vegetarien) c.push('végétarien');
    if (this.genForm.sans_gluten) c.push('sans gluten');
    if (this.genForm.halal) c.push('halal');
    return c;
  }

  generer(): void {
    if (!this.genForm.demande.trim()) return;
    this.generation.set(true);
    this.error.set(null);
    this.api.genererRecette(this.genForm.demande, this.genForm.nb_portions, this.contraintes())
      .subscribe({
        next: p => {
          this.proposee.set(p);
          this.platForm = {
            creer: true, nom: p.nom, description: '', prix_unitaire: 0, sous_categorie: null,
          };
          this.generation.set(false);
          this.showGenModal.set(false);
          this.showApercu.set(true);
        },
        error: err => {
          this.generation.set(false);
          this.error.set(err.error?.detail ?? `Erreur de génération : ${err.status}`);
        },
      });
  }

  enregistrerGeneree(): void {
    const p = this.proposee();
    if (!p) return;
    this.api.enregistrerRecetteGeneree({
      nom: p.nom,
      instructions_html: p.instructions_html,
      temps_preparation: p.temps_preparation,
      nb_portions: p.nb_portions,
      ingredients: p.ingredients.map(i => ({ nom: i.nom, quantite: i.quantite, unite: i.unite })),
      plat: {
        creer: this.platForm.creer,
        nom: this.platForm.nom,
        description: this.platForm.description,
        prix_unitaire: this.platForm.prix_unitaire,
        sous_categorie: this.platForm.sous_categorie,
        sans_gluten: this.genForm.sans_gluten,
        vegetarien: this.genForm.vegetarien,
        halal: this.genForm.halal,
      },
    }).subscribe({
      next: () => {
        this.showApercu.set(false);
        this.proposee.set(null);
        this.load();
        this.api.getIngredients().subscribe({ next: i => this.ingredients.set(i) });
      },
      error: err => this.error.set(err.error?.detail ?? `Erreur d'enregistrement : ${err.status}`),
    });
  }

  fermerApercu(): void {
    this.showApercu.set(false);
    this.proposee.set(null);
  }

  nbACreer(): number {
    return (this.proposee()?.ingredients ?? []).filter(i => !i.existant).length;
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
