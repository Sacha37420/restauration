import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

interface EnvWindow {
  __env?: { apiUrl?: string };
}

export interface Fournisseur {
  id?: number; nom: string; email?: string; telephone?: string; commentaire?: string;
}
export interface Unite {
  id?: number; nom: string; description?: string;
}
export interface Ingredient {
  id?: number; nom: string; quantite_stock: number; seuil_alerte?: number | null;
  fournisseur?: number | null; unite: number; sous_seuil?: boolean;
  fournisseur_detail?: Fournisseur; unite_detail?: Unite;
}
export interface LigneRecette {
  id?: number; ingredient: number; quantite: number;
}
export interface Recette {
  id?: number; nom: string; instructions_html: string; temps_preparation: number;
  nb_portions: number; lignes_recette?: LigneRecette[];
}
export interface CategoriePlatSimple {
  id?: number; nom: string; ordre: number;
}
export interface SousCategoriePlatInline {
  id?: number; nom: string; ordre: number;
}
export interface CategoriePlat {
  id?: number; nom: string; ordre: number;
  sous_categories?: SousCategoriePlatInline[];
}
export interface SousCategoriePlat {
  id?: number; categorie: number; nom: string; ordre: number;
  categorie_detail?: CategoriePlatSimple;
}

export interface Plat {
  id?: number; nom: string; description?: string; photo?: string | null;
  prix_unitaire: number; sans_gluten: boolean; halal: boolean;
  vegetarien: boolean; actif: boolean; recette?: number | null;
  sous_categorie?: number | null;
  sous_categorie_detail?: SousCategoriePlat | null;
}
export interface StockPlat {
  id?: number; plat: number; quantite_disponible: number; date_production: string;
}
export interface TableRestaurant {
  id?: number; numero: number; token_qr: string; actif: boolean;
  pos_x?: number | null; pos_y?: number | null;
}
export interface CanalCommande {
  id?: number; nom: string; description?: string;
}
export interface StatutCommande {
  id?: number; nom: string; description?: string;
}
export interface StatutPaiement {
  id?: number; nom: string; description?: string;
}
export interface LigneCommande {
  id?: number; plat: number; quantite: number; prix_unitaire_snapshot: number;
}
export interface PaiementInline {
  id?: number; statut: number; statut_detail?: StatutPaiement;
  montant: number; methode: string; transaction_id?: string;
  confirme_par?: string; created_at?: string;
}
export interface Commande {
  id?: number; canal: number; statut: number; table_restaurant?: number | null;
  compte_client?: number | null; numero_table?: number | null;
  created_at?: string; lignes_commande?: LigneCommande[];
  canal_detail?: CanalCommande; statut_detail?: StatutCommande;
  paiement?: PaiementInline | null;
}
export interface Paiement {
  id?: number; commande: number; statut: number; montant: number;
  methode: string; transaction_id?: string; confirme_par?: string; created_at?: string;
}
export interface Employe {
  id?: number; user: number; role: string;
}
export interface PlageTravail {
  id?: number; employe: number; debut: string; fin: string; note?: string;
}
export interface MouvementStock {
  id?: number; ingredient: number; employe?: number | null;
  type: string; quantite: number; date?: string; raison?: string;
}
export interface ConfigurationStripe {
  stripe_secret_key: string;
  stripe_webhook_secret: string;
  updated_at?: string;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);

  private get base(): string {
    return (window as unknown as EnvWindow).__env?.apiUrl ?? 'http://localhost:8088';
  }

  private url(path: string): string {
    return `${this.base}/api/${path}`;
  }

  private urlPublic(path: string): string {
    return `${this.base}/api/public/${path}`;
  }

  // Catégories et sous-catégories de plats
  getCategories(): Observable<CategoriePlat[]> {
    return this.http.get<CategoriePlat[]>(this.url('categories-plat/'));
  }
  createCategorie(data: Partial<CategoriePlat>): Observable<CategoriePlat> {
    return this.http.post<CategoriePlat>(this.url('categories-plat/'), data);
  }
  updateCategorie(id: number, data: Partial<CategoriePlat>): Observable<CategoriePlat> {
    return this.http.put<CategoriePlat>(this.url(`categories-plat/${id}/`), data);
  }
  deleteCategorie(id: number): Observable<void> {
    return this.http.delete<void>(this.url(`categories-plat/${id}/`));
  }
  getSousCategories(): Observable<SousCategoriePlat[]> {
    return this.http.get<SousCategoriePlat[]>(this.url('sous-categories-plat/'));
  }
  createSousCategorie(data: Partial<SousCategoriePlat>): Observable<SousCategoriePlat> {
    return this.http.post<SousCategoriePlat>(this.url('sous-categories-plat/'), data);
  }
  updateSousCategorie(id: number, data: Partial<SousCategoriePlat>): Observable<SousCategoriePlat> {
    return this.http.put<SousCategoriePlat>(this.url(`sous-categories-plat/${id}/`), data);
  }
  deleteSousCategorie(id: number): Observable<void> {
    return this.http.delete<void>(this.url(`sous-categories-plat/${id}/`));
  }

  // Fournisseurs
  getFournisseurs(): Observable<Fournisseur[]> {
    return this.http.get<Fournisseur[]>(this.url('fournisseurs/'));
  }
  createFournisseur(data: Fournisseur): Observable<Fournisseur> {
    return this.http.post<Fournisseur>(this.url('fournisseurs/'), data);
  }
  updateFournisseur(id: number, data: Fournisseur): Observable<Fournisseur> {
    return this.http.put<Fournisseur>(this.url(`fournisseurs/${id}/`), data);
  }
  deleteFournisseur(id: number): Observable<void> {
    return this.http.delete<void>(this.url(`fournisseurs/${id}/`));
  }

  // Unités
  getUnites(): Observable<Unite[]> {
    return this.http.get<Unite[]>(this.url('unites/'));
  }
  createUnite(data: Unite): Observable<Unite> {
    return this.http.post<Unite>(this.url('unites/'), data);
  }
  updateUnite(id: number, data: Unite): Observable<Unite> {
    return this.http.put<Unite>(this.url(`unites/${id}/`), data);
  }
  deleteUnite(id: number): Observable<void> {
    return this.http.delete<void>(this.url(`unites/${id}/`));
  }

  // Ingrédients
  getIngredients(sousSeuil?: boolean): Observable<Ingredient[]> {
    let params = new HttpParams();
    if (sousSeuil) params = params.set('sous_seuil', 'true');
    return this.http.get<Ingredient[]>(this.url('ingredients/'), { params });
  }
  getIngredient(id: number): Observable<Ingredient> {
    return this.http.get<Ingredient>(this.url(`ingredients/${id}/`));
  }
  createIngredient(data: Partial<Ingredient>): Observable<Ingredient> {
    return this.http.post<Ingredient>(this.url('ingredients/'), data);
  }
  updateIngredient(id: number, data: Partial<Ingredient>): Observable<Ingredient> {
    return this.http.put<Ingredient>(this.url(`ingredients/${id}/`), data);
  }
  deleteIngredient(id: number): Observable<void> {
    return this.http.delete<void>(this.url(`ingredients/${id}/`));
  }

  // Recettes
  getRecettes(): Observable<Recette[]> {
    return this.http.get<Recette[]>(this.url('recettes/'));
  }
  getRecette(id: number): Observable<Recette> {
    return this.http.get<Recette>(this.url(`recettes/${id}/`));
  }
  createRecette(data: Partial<Recette>): Observable<Recette> {
    return this.http.post<Recette>(this.url('recettes/'), data);
  }
  updateRecette(id: number, data: Partial<Recette>): Observable<Recette> {
    return this.http.put<Recette>(this.url(`recettes/${id}/`), data);
  }
  deleteRecette(id: number): Observable<void> {
    return this.http.delete<void>(this.url(`recettes/${id}/`));
  }
  getLignesRecette(id: number): Observable<LigneRecette[]> {
    return this.http.get<LigneRecette[]>(this.url(`recettes/${id}/lignes/`));
  }
  addLigneRecette(id: number, data: LigneRecette): Observable<LigneRecette> {
    return this.http.post<LigneRecette>(this.url(`recettes/${id}/lignes/`), data);
  }
  deleteLigneRecette(recetteId: number, ligneId: number): Observable<void> {
    return this.http.delete<void>(this.url(`recettes/${recetteId}/lignes/${ligneId}/`));
  }

  // Plats
  getPlats(filters?: Partial<{actif: boolean; sans_gluten: boolean; halal: boolean; vegetarien: boolean}>): Observable<Plat[]> {
    let params = new HttpParams();
    if (filters) {
      for (const [k, v] of Object.entries(filters)) {
        if (v !== undefined) params = params.set(k, String(v));
      }
    }
    return this.http.get<Plat[]>(this.url('plats/'), { params });
  }
  createPlat(data: FormData | Partial<Plat>): Observable<Plat> {
    return this.http.post<Plat>(this.url('plats/'), data);
  }
  updatePlat(id: number, data: FormData | Partial<Plat>): Observable<Plat> {
    return this.http.put<Plat>(this.url(`plats/${id}/`), data);
  }
  deletePlat(id: number): Observable<void> {
    return this.http.delete<void>(this.url(`plats/${id}/`));
  }

  // Tables
  getTables(): Observable<TableRestaurant[]> {
    return this.http.get<TableRestaurant[]>(this.url('tables/'));
  }
  createTable(data: Partial<TableRestaurant>): Observable<TableRestaurant> {
    return this.http.post<TableRestaurant>(this.url('tables/'), data);
  }
  updateTable(id: number, data: Partial<TableRestaurant>): Observable<TableRestaurant> {
    return this.http.put<TableRestaurant>(this.url(`tables/${id}/`), data);
  }
  deleteTable(id: number): Observable<void> {
    return this.http.delete<void>(this.url(`tables/${id}/`));
  }

  // Canaux / Statuts
  getCanaux(): Observable<CanalCommande[]> {
    return this.http.get<CanalCommande[]>(this.url('canaux-commande/'));
  }
  getStatutsCommande(): Observable<StatutCommande[]> {
    return this.http.get<StatutCommande[]>(this.url('statuts-commande/'));
  }
  getStatutsPaiement(): Observable<StatutPaiement[]> {
    return this.http.get<StatutPaiement[]>(this.url('statuts-paiement/'));
  }

  // Commandes
  getCommandes(filters?: { statut?: number; canal?: number; date_debut?: string; date_fin?: string; numero_table?: number; limit?: number }): Observable<Commande[]> {
    let params = new HttpParams();
    if (filters) {
      for (const [k, v] of Object.entries(filters)) {
        if (v !== undefined && v !== null && v !== '') params = params.set(k, String(v));
      }
    }
    return this.http.get<Commande[]>(this.url('commandes/'), { params });
  }
  getCommande(id: number): Observable<Commande> {
    return this.http.get<Commande>(this.url(`commandes/${id}/`));
  }
  createCommande(data: Partial<Commande>): Observable<Commande> {
    return this.http.post<Commande>(this.url('commandes/'), data);
  }
  updateCommande(id: number, data: Partial<Commande>): Observable<Commande> {
    return this.http.patch<Commande>(this.url(`commandes/${id}/`), data);
  }
  addLigneCommande(commandeId: number, data: Partial<LigneCommande>): Observable<LigneCommande> {
    return this.http.post<LigneCommande>(this.url(`commandes/${commandeId}/lignes/`), data);
  }
  deleteLigneCommande(commandeId: number, ligneId: number): Observable<void> {
    return this.http.delete<void>(this.url(`commandes/${commandeId}/lignes/${ligneId}/`));
  }

  // Paiements
  getPaiements(): Observable<Paiement[]> {
    return this.http.get<Paiement[]>(this.url('paiements/'));
  }
  createPaiement(data: Partial<Paiement>): Observable<Paiement> {
    return this.http.post<Paiement>(this.url('paiements/'), data);
  }
  updatePaiement(id: number, data: Partial<Paiement>): Observable<Paiement> {
    return this.http.patch<Paiement>(this.url(`paiements/${id}/`), data);
  }
  // Encaissement sur place par un employé (liquide, ticket resto…) — aucun frais Stripe
  confirmerPaiementSurPlace(commandeId: number, methode: string): Observable<Paiement> {
    return this.http.post<Paiement>(this.url(`commandes/${commandeId}/confirmer-paiement/`), { methode });
  }

  // API publique (sans auth — table client)
  publicGetPlats(): Observable<Plat[]> {
    return this.http.get<Plat[]>(this.urlPublic('plats/'));
  }
  publicCreateCommande(numeroTable: number): Observable<Commande> {
    return this.http.post<Commande>(this.urlPublic('commandes/'), { numero_table: numeroTable });
  }
  publicGetCommande(id: number): Observable<Commande> {
    return this.http.get<Commande>(this.urlPublic(`commandes/${id}/`));
  }
  publicAddLigne(commandeId: number, platId: number, quantite: number): Observable<LigneCommande> {
    return this.http.post<LigneCommande>(this.urlPublic(`commandes/${commandeId}/lignes/`), { plat: platId, quantite });
  }
  publicDeleteLigne(commandeId: number, ligneId: number): Observable<void> {
    return this.http.delete<void>(this.urlPublic(`commandes/${commandeId}/lignes/${ligneId}/`));
  }
  publicPayer(commandeId: number, methode: string): Observable<Paiement> {
    return this.http.post<Paiement>(this.urlPublic(`commandes/${commandeId}/payer/`), { methode });
  }
  publicStripeCheckout(commandeId: number): Observable<{ checkout_url: string }> {
    return this.http.post<{ checkout_url: string }>(this.urlPublic(`commandes/${commandeId}/stripe-checkout/`), {});
  }

  // Employés
  getEmployes(): Observable<Employe[]> {
    return this.http.get<Employe[]>(this.url('employes/'));
  }

  // Planning
  getPlagesTravail(employeId?: number): Observable<PlageTravail[]> {
    let params = new HttpParams();
    if (employeId) params = params.set('employe', String(employeId));
    return this.http.get<PlageTravail[]>(this.url('plages-travail/'), { params });
  }
  createPlageTravail(data: Partial<PlageTravail>): Observable<PlageTravail> {
    return this.http.post<PlageTravail>(this.url('plages-travail/'), data);
  }
  updatePlageTravail(id: number, data: Partial<PlageTravail>): Observable<PlageTravail> {
    return this.http.put<PlageTravail>(this.url(`plages-travail/${id}/`), data);
  }
  deletePlageTravail(id: number): Observable<void> {
    return this.http.delete<void>(this.url(`plages-travail/${id}/`));
  }

  // Mouvements de stock
  getMouvementsStock(ingredientId?: number): Observable<MouvementStock[]> {
    let params = new HttpParams();
    if (ingredientId) params = params.set('ingredient', String(ingredientId));
    return this.http.get<MouvementStock[]>(this.url('mouvements-stock/'), { params });
  }
  createMouvementStock(data: Partial<MouvementStock>): Observable<MouvementStock> {
    return this.http.post<MouvementStock>(this.url('mouvements-stock/'), data);
  }

  // Stripe
  getConfigurationStripe(): Observable<ConfigurationStripe> {
    return this.http.get<ConfigurationStripe>(this.url('stripe/configuration/'));
  }
  updateConfigurationStripe(data: Partial<ConfigurationStripe>): Observable<ConfigurationStripe> {
    return this.http.put<ConfigurationStripe>(this.url('stripe/configuration/'), data);
  }
  creerSessionCheckout(commandeId: number): Observable<{ checkout_url: string }> {
    return this.http.post<{ checkout_url: string }>(this.url('stripe/checkout/'), { commande_id: commandeId });
  }
}
