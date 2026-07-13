import { Component, inject, OnInit, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  ApiService, Ingredient, Fournisseur, Unite, ArticleFournisseur, PrixArticle,
} from '../../core/api.service';

@Component({
  selector: 'app-ingredients',
  standalone: true,
  imports: [FormsModule, DatePipe],
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

  // Catalogue : articles fournisseur de l'ingrédient sélectionné.
  showArticlesModal = signal(false);
  articles = signal<ArticleFournisseur[]>([]);
  articlesLoading = signal(false);
  editingArticle = signal<ArticleFournisseur | null>(null);
  showArticleForm = signal(false);
  articlePourPrix = signal<ArticleFournisseur | null>(null);

  form: Partial<Ingredient> = {};
  mouvForm = { type: 'entree', quantite: 0, raison: '' };
  articleForm: Partial<ArticleFournisseur> = {};
  /** Tarif saisi à la création d'un article (évite un aller-retour de plus). */
  prixInitial: number | null = null;
  prixForm: Partial<PrixArticle> = { quantite_min: 1, prix_ht: 0 };

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
    this.form = { nom: '', quantite_stock: 0, seuil_alerte: null, unite: undefined as unknown as number };
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

  // ----- Articles fournisseur -----

  openArticles(item: Ingredient): void {
    this.selectedIngredient.set(item);
    this.showArticlesModal.set(true);
    this.showArticleForm.set(false);
    this.articlePourPrix.set(null);
    this.loadArticles();
  }

  loadArticles(): void {
    const ing = this.selectedIngredient();
    if (!ing?.id) return;
    this.articlesLoading.set(true);
    this.api.getArticlesFournisseur({ ingredient: ing.id }).subscribe({
      next: a => { this.articles.set(a); this.articlesLoading.set(false); },
      error: err => { this.error.set(`Erreur ${err.status}`); this.articlesLoading.set(false); },
    });
  }

  openCreateArticle(): void {
    const ing = this.selectedIngredient();
    this.articleForm = {
      ingredient: ing?.id,
      libelle: ing?.nom ?? '',
      unite: ing?.unite,            // par défaut l'unité de l'ingrédient
      quantite_conditionnement: 1,
      disponible: true,
      prefere: false,
      fournisseur: undefined as unknown as number,
    };
    this.prixInitial = null;
    this.editingArticle.set(null);
    this.showArticleForm.set(true);
  }

  openEditArticle(article: ArticleFournisseur): void {
    this.articleForm = { ...article };
    this.prixInitial = null;
    this.editingArticle.set(article);
    this.showArticleForm.set(true);
  }

  saveArticle(): void {
    const existant = this.editingArticle();
    if (existant?.id) {
      this.api.updateArticleFournisseur(existant.id, this.articleForm).subscribe({
        next: () => { this.showArticleForm.set(false); this.loadArticles(); this.load(); },
        error: err => this.error.set(`Erreur enregistrement article : ${err.status}`),
      });
      return;
    }
    this.api.createArticleFournisseur(this.articleForm).subscribe({
      next: cree => {
        if (this.prixInitial == null || !cree.id) {
          this.showArticleForm.set(false);
          this.loadArticles();
          this.load();
          return;
        }
        this.api.ajouterPrixArticle(cree.id, { quantite_min: 1, prix_ht: this.prixInitial })
          .subscribe({
            next: () => { this.showArticleForm.set(false); this.loadArticles(); this.load(); },
            error: err => this.error.set(`Article créé, mais tarif refusé : ${err.status}`),
          });
      },
      error: err => this.error.set(`Erreur création article : ${err.status}`),
    });
  }

  deleteArticle(article: ArticleFournisseur): void {
    if (!confirm(`Supprimer l'article "${article.libelle}" et son historique de prix ?`)) return;
    this.api.deleteArticleFournisseur(article.id!).subscribe({
      next: () => { this.loadArticles(); this.load(); },
    });
  }

  openPrix(article: ArticleFournisseur): void {
    this.articlePourPrix.set(article);
    this.prixForm = { quantite_min: 1, prix_ht: 0 };
  }

  savePrix(): void {
    const article = this.articlePourPrix();
    if (!article?.id) return;
    this.api.ajouterPrixArticle(article.id, this.prixForm).subscribe({
      next: () => { this.articlePourPrix.set(null); this.loadArticles(); this.load(); },
      error: err => this.error.set(`Erreur ajout tarif : ${err.status}`),
    });
  }

  closeArticles(): void {
    this.showArticlesModal.set(false);
    this.showArticleForm.set(false);
    this.articlePourPrix.set(null);
  }

  close(): void { this.showModal.set(false); this.showMouvModal.set(false); }
}
