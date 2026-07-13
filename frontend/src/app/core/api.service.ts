import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

interface EnvWindow {
  __env?: { apiUrl?: string };
}

export interface Fournisseur {
  id?: number; nom: string; email?: string; telephone?: string; commentaire?: string;
  // Accès au portail, pour le robot de catalogue.
  url?: string; identifiant?: string;
  /** Écriture seule. Vide = « ne change rien » (le serveur ne le renvoie jamais). */
  mot_de_passe?: string;
  mot_de_passe_defini?: boolean; robot_pret?: boolean;
  /** Mistral rattache les articles rapportés à un ingrédient (ou en crée un). */
  rattachement_auto?: boolean;
  /** Sert au robot quand le site exige un magasin/drive pour afficher ses prix. */
  code_postal?: string;
  /** Écriture seule : état du navigateur (cookies + localStorage). Jamais relu. */
  session_state?: string;
  session_memorisee?: boolean;
}
export interface SynchroCatalogue {
  id?: number; fournisseur: number; fournisseur_nom?: string;
  statut: 'en_cours' | 'succes' | 'echec';
  etape?: string; message?: string;
  pages_scannees?: number; appels_mistral?: number;
  articles_crees?: number; articles_maj?: number; prix_releves?: number;
  articles_rattaches?: number; ingredients_crees?: number; articles_ignores?: number;
  journal?: string[]; demarre_le?: string; termine_le?: string | null;
}
export interface Unite {
  id?: number; nom: string; description?: string;
}
export interface Ingredient {
  id?: number; nom: string; quantite_stock: number; seuil_alerte?: number | null;
  unite: number; sous_seuil?: boolean;
  // Agrégats calculés côté serveur à partir des articles fournisseur.
  nb_articles?: number; fournisseurs?: string[]; meilleur_prix_unitaire?: string | null;
  unite_detail?: Unite; articles?: ArticleFournisseur[];
}
export interface PrixArticle {
  id?: number; article?: number; quantite_min: number | string; prix_ht: number | string;
  taux_tva?: number | string; releve_le?: string; source?: string;
}
export interface ArticleFournisseur {
  id?: number; fournisseur: number; ingredient?: number | null;
  libelle: string; reference?: string; ean?: string; marque?: string;
  conditionnement?: string; quantite_conditionnement: number | string; unite: number;
  disponible?: boolean; prefere?: boolean; url?: string; source?: string;
  synchronise_le?: string | null;
  prix_actuel?: string | null; prix_unitaire?: string | null;
  fournisseur_detail?: Fournisseur; unite_detail?: Unite; prix?: PrixArticle[];
}
export interface LigneRecette {
  id?: number; ingredient: number; quantite: number;
}
export interface Recette {
  id?: number; nom: string; instructions_html: string; temps_preparation: number;
  nb_portions: number; lignes_recette?: LigneRecette[];
  /** Chiffré au meilleur prix fournisseur. null si un ingrédient n'a pas de prix. */
  cout_matiere?: string | null; cout_par_portion?: string | null;
}
export interface IngredientPropose {
  nom: string; quantite: string; unite: string;
  existant: boolean;
  /** L'unité proposée par Mistral n'était pas dans la liste autorisée. */
  unite_corrigee?: boolean; unite_proposee?: string;
  prix_unitaire?: string | null; cout?: string | null;
}
export interface RecetteProposee {
  nom: string; temps_preparation: number; nb_portions: number; instructions_html: string;
  ingredients: IngredientPropose[];
  cout_matiere?: string | null; cout_par_portion?: string | null; cout_incomplet?: boolean;
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
  prix_unitaire: number; taux_tva?: number; sans_gluten: boolean; halal: boolean;
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
export interface Facture {
  id?: number; commande: number; numero: string; montant_ttc: number;
  taux_tva: number; email_destinataire?: string; envoyee_at?: string | null;
  created_at?: string;
}
export interface ConfigurationEmail {
  actif: boolean; email_host: string; email_port: number; email_use_tls: boolean;
  email_host_user: string; email_host_password: string; default_from_email: string;
  updated_at?: string;
}
export interface Utilisateur {
  id?: string;
  email: string;
  prenom: string;
  nom: string;
  roles: string[];
  enabled?: boolean;
  invitation_envoyee?: boolean;
  detail?: string;
}
/** Accès à l'API Mistral — partagé par les 3 usages (robot, recettes, événements). */
export interface ConfigurationMistral {
  actif: boolean; api_key: string; modele: string; updated_at?: string;
}
/** Un prompt par usage. `contenu` vide côté serveur = le défaut du code s'applique. */
export interface PromptMistral {
  usage: string; libelle: string; contenu: string; par_defaut: string;
  personnalise: boolean; updated_at?: string | null;
}
/** Paramètres propres à l'agent calendrier : ville et période ciblées. */
export interface ConfigurationAgentEvenements {
  ville: string; mois: number | null; annee: number | null; updated_at?: string;
}
export interface StationMeteo {
  id_station: string; nom: string; departement: string;
  altitude?: number | null; distance_km: number;
}
/** Une station essayée : retenue, ou écartée avec sa raison. */
export interface TentativeStation {
  station: string; id_station: string; distance_km: number;
  retenue?: boolean; releves?: number; echec?: string;
}
export interface RecuperationMeteo {
  detail: string; count: number;
  station: StationMeteo;
  stations_ecartees: TentativeStation[];
  tentatives: TentativeStation[];
}
export interface CatalogueStations {
  total: number; ouvertes?: number; maj_le?: string | null;
  ville?: string; lat?: number; lon?: number;
  stations?: StationMeteo[];
}
export interface ConfigurationMeteo {
  actif: boolean; api_key: string; ville: string;
  mois: number | null; annee: number | null; updated_at?: string;
}
export interface Evenement {
  id?: number; ville: string; titre: string; date_debut: string; date_fin: string;
  surplus_frequentation: number; confiance?: string; source?: string; created_at?: string;
}
export interface DonneeMeteoHoraire {
  id?: number; ville: string; horodatage: string;
  temperature: number | null; nebulosite: number | null; precipitation: number | null;
  source?: string;
}
export interface IndicateurMeteoConfig {
  id?: number; nom: string; champ: string; agregation: string;
  heure_debut: number; heure_fin: number; actif: boolean;
}
export interface IndicateursJournaliers {
  indicateurs: { nom: string; champ: string; agregation: string; heure_debut: number; heure_fin: number }[];
  jours: { date: string; valeurs: Record<string, number | null> }[];
}
export interface VenteAgregee {
  id?: number; date: string; categorie: number | null; categorie_nom?: string;
  montant_ht: number; montant_ttc: number; quantite: number; source?: string;
}
export interface RegressionResultat {
  cible: string; n: number; features: string[];
  r2: number | null; r2_adj: number | null; f_pvalue: number | null;
  viable: boolean; verdict: string;
  coefficients: { nom: string; coef: number | null; p_value: number | null; significatif: boolean }[];
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

  // Robot de catalogue
  /** Lance le robot en tâche de fond ; suivre ensuite avec getSynchro(). */
  synchroniserFournisseur(id: number): Observable<SynchroCatalogue> {
    return this.http.post<SynchroCatalogue>(this.url(`fournisseurs/${id}/synchroniser/`), {});
  }
  /** Vide le cache de XPath : la prochaine synchro redécouvrira le site via Mistral. */
  oublierSelecteurs(id: number): Observable<void> {
    return this.http.post<void>(this.url(`fournisseurs/${id}/oublier-selecteurs/`), {});
  }
  /** Efface la session mémorisée (magasin choisi, cookies, connexion). */
  oublierSession(id: number): Observable<void> {
    return this.http.post<void>(this.url(`fournisseurs/${id}/oublier-session/`), {});
  }
  getSynchro(id: number): Observable<SynchroCatalogue> {
    return this.http.get<SynchroCatalogue>(this.url(`synchros-catalogue/${id}/`));
  }
  getSynchros(fournisseurId?: number): Observable<SynchroCatalogue[]> {
    let params = new HttpParams();
    if (fournisseurId) params = params.set('fournisseur', String(fournisseurId));
    return this.http.get<SynchroCatalogue[]>(this.url('synchros-catalogue/'), { params });
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

  // Articles fournisseur (catalogue)
  getArticlesFournisseur(filtres?: {
    fournisseur?: number; ingredient?: number; sansIngredient?: boolean; q?: string;
  }): Observable<ArticleFournisseur[]> {
    let params = new HttpParams();
    if (filtres?.fournisseur) params = params.set('fournisseur', String(filtres.fournisseur));
    if (filtres?.ingredient) params = params.set('ingredient', String(filtres.ingredient));
    if (filtres?.sansIngredient) params = params.set('sans_ingredient', 'true');
    if (filtres?.q) params = params.set('q', filtres.q);
    return this.http.get<ArticleFournisseur[]>(this.url('articles-fournisseur/'), { params });
  }
  createArticleFournisseur(data: Partial<ArticleFournisseur>): Observable<ArticleFournisseur> {
    return this.http.post<ArticleFournisseur>(this.url('articles-fournisseur/'), data);
  }
  updateArticleFournisseur(id: number, data: Partial<ArticleFournisseur>): Observable<ArticleFournisseur> {
    return this.http.put<ArticleFournisseur>(this.url(`articles-fournisseur/${id}/`), data);
  }
  deleteArticleFournisseur(id: number): Observable<void> {
    return this.http.delete<void>(this.url(`articles-fournisseur/${id}/`));
  }
  /** Ajoute un relevé de tarif (historisé — n'écrase pas le précédent). */
  ajouterPrixArticle(articleId: number, data: Partial<PrixArticle>): Observable<ArticleFournisseur> {
    return this.http.post<ArticleFournisseur>(
      this.url(`articles-fournisseur/${articleId}/prix/`), data);
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

  // Génération de recette (Mistral) — propose, puis l'utilisateur valide.
  genererRecette(demande: string, nbPortions: number, contraintes: string[]): Observable<RecetteProposee> {
    return this.http.post<RecetteProposee>(this.url('recettes/generer/'), {
      demande, nb_portions: nbPortions, contraintes,
    });
  }
  enregistrerRecetteGeneree(payload: {
    nom: string; instructions_html: string; temps_preparation: number; nb_portions: number;
    ingredients: { nom: string; quantite: string | number; unite: string }[];
    plat?: {
      creer: boolean; nom?: string; description?: string; prix_unitaire?: number;
      sous_categorie?: number | null; sans_gluten?: boolean; vegetarien?: boolean; halal?: boolean;
    };
  }): Observable<{ recette: Recette; plat: Plat | null }> {
    return this.http.post<{ recette: Recette; plat: Plat | null }>(
      this.url('recettes/enregistrer-generee/'), payload);
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
  publicCreateCommande(numeroTable: number, email?: string): Observable<Commande> {
    return this.http.post<Commande>(this.urlPublic('commandes/'), { numero_table: numeroTable, email });
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
  publicPayer(commandeId: number, methode: string, email?: string): Observable<Paiement> {
    return this.http.post<Paiement>(this.urlPublic(`commandes/${commandeId}/payer/`), { methode, email });
  }
  publicStripeCheckout(commandeId: number, email?: string): Observable<{ checkout_url: string }> {
    return this.http.post<{ checkout_url: string }>(this.urlPublic(`commandes/${commandeId}/stripe-checkout/`), { email });
  }

  // Factures (PDF généré localement, gratuit ; envoi par email optionnel)
  getFacture(commandeId: number): Observable<Facture> {
    return this.http.get<Facture>(this.url(`commandes/${commandeId}/facture/`));
  }
  genererFacture(commandeId: number, email?: string): Observable<Facture> {
    return this.http.post<Facture>(this.url(`commandes/${commandeId}/facture/`), email ? { email } : {});
  }
  telechargerFacturePdf(commandeId: number): Observable<Blob> {
    return this.http.get(this.url(`commandes/${commandeId}/facture/pdf/`), { responseType: 'blob' });
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

  // Email / SMTP
  getConfigurationEmail(): Observable<ConfigurationEmail> {
    return this.http.get<ConfigurationEmail>(this.url('email/configuration/'));
  }
  updateConfigurationEmail(data: Partial<ConfigurationEmail>): Observable<ConfigurationEmail> {
    return this.http.put<ConfigurationEmail>(this.url('email/configuration/'), data);
  }
  testEmail(destinataire: string): Observable<{ detail: string }> {
    return this.http.post<{ detail: string }>(this.url('email/test/'), { destinataire });
  }

  // Utilisateurs (gestion par les managers)
  getUtilisateurs(): Observable<Utilisateur[]> {
    return this.http.get<Utilisateur[]>(this.url('utilisateurs/'));
  }
  createUtilisateur(data: { email: string; prenom: string; nom: string; roles: string[] }): Observable<Utilisateur> {
    return this.http.post<Utilisateur>(this.url('utilisateurs/'), data);
  }
  updateRolesUtilisateur(id: string, roles: string[]): Observable<{ id: string; roles: string[] }> {
    return this.http.put<{ id: string; roles: string[] }>(this.url(`utilisateurs/${id}/roles/`), { roles });
  }
  inviterUtilisateur(id: string): Observable<{ detail: string }> {
    return this.http.post<{ detail: string }>(this.url(`utilisateurs/${id}/inviter/`), {});
  }
  setEtatUtilisateur(id: string, enabled: boolean): Observable<{ id: string; enabled: boolean }> {
    return this.http.post<{ id: string; enabled: boolean }>(this.url(`utilisateurs/${id}/etat/`), { enabled });
  }

  // Mistral — accès partagé par le robot fournisseur, les recettes et les événements
  getConfigurationMistral(): Observable<ConfigurationMistral> {
    return this.http.get<ConfigurationMistral>(this.url('mistral/configuration/'));
  }
  updateConfigurationMistral(data: Partial<ConfigurationMistral>): Observable<ConfigurationMistral> {
    return this.http.put<ConfigurationMistral>(this.url('mistral/configuration/'), data);
  }
  getPromptsMistral(): Observable<PromptMistral[]> {
    return this.http.get<PromptMistral[]>(this.url('mistral/prompts/'));
  }
  updatePromptMistral(usage: string, contenu: string): Observable<PromptMistral> {
    return this.http.put<PromptMistral>(this.url('mistral/prompts/'), { usage, contenu });
  }
  /** Supprime la surcharge : le prompt par défaut reprend la main. */
  resetPromptMistral(usage: string): Observable<PromptMistral> {
    return this.http.delete<PromptMistral>(this.url(`mistral/prompts/?usage=${usage}`));
  }

  // Agent calendrier d'événements — ville et période ciblées
  getConfigurationAgent(): Observable<ConfigurationAgentEvenements> {
    return this.http.get<ConfigurationAgentEvenements>(this.url('agent-evenements/configuration/'));
  }
  updateConfigurationAgent(data: Partial<ConfigurationAgentEvenements>): Observable<ConfigurationAgentEvenements> {
    return this.http.put<ConfigurationAgentEvenements>(this.url('agent-evenements/configuration/'), data);
  }

  // Météo-France
  getConfigurationMeteo(): Observable<ConfigurationMeteo> {
    return this.http.get<ConfigurationMeteo>(this.url('meteo/configuration/'));
  }
  updateConfigurationMeteo(data: Partial<ConfigurationMeteo>): Observable<ConfigurationMeteo> {
    return this.http.put<ConfigurationMeteo>(this.url('meteo/configuration/'), data);
  }

  // Analyse économique — Événements
  getEvenements(filters?: { ville?: string; annee?: number; mois?: number }): Observable<Evenement[]> {
    let params = new HttpParams();
    if (filters) {
      for (const [k, v] of Object.entries(filters)) {
        if (v !== undefined && v !== null && v !== '') params = params.set(k, String(v));
      }
    }
    return this.http.get<Evenement[]>(this.url('analyse/evenements/'), { params });
  }
  createEvenement(data: Evenement): Observable<Evenement> {
    return this.http.post<Evenement>(this.url('analyse/evenements/'), data);
  }
  updateEvenement(id: number, data: Evenement): Observable<Evenement> {
    return this.http.put<Evenement>(this.url(`analyse/evenements/${id}/`), data);
  }
  deleteEvenement(id: number): Observable<void> {
    return this.http.delete<void>(this.url(`analyse/evenements/${id}/`));
  }
  proposerEvenementsMistral(body: { ville: string; mois?: number | null; annee: number }): Observable<{ evenements: Evenement[] }> {
    return this.http.post<{ evenements: Evenement[] }>(this.url('analyse/evenements/proposer-mistral/'), body);
  }
  enregistrerEvenementsLot(evenements: Evenement[]): Observable<Evenement[]> {
    return this.http.post<Evenement[]>(this.url('analyse/evenements/enregistrer-lot/'), { evenements });
  }

  // Analyse économique — Météo
  getMeteoHoraire(filters?: { ville?: string; date?: string; annee?: number; mois?: number }): Observable<DonneeMeteoHoraire[]> {
    let params = new HttpParams();
    if (filters) {
      for (const [k, v] of Object.entries(filters)) {
        if (v !== undefined && v !== null && v !== '') params = params.set(k, String(v));
      }
    }
    return this.http.get<DonneeMeteoHoraire[]>(this.url('analyse/meteo-horaire/'), { params });
  }
  createMeteoHoraire(data: DonneeMeteoHoraire): Observable<DonneeMeteoHoraire> {
    return this.http.post<DonneeMeteoHoraire>(this.url('analyse/meteo-horaire/'), data);
  }
  updateMeteoHoraire(id: number, data: DonneeMeteoHoraire): Observable<DonneeMeteoHoraire> {
    return this.http.put<DonneeMeteoHoraire>(this.url(`analyse/meteo-horaire/${id}/`), data);
  }
  deleteMeteoHoraire(id: number): Observable<void> {
    return this.http.delete<void>(this.url(`analyse/meteo-horaire/${id}/`));
  }
  recupererMeteo(body: { ville: string; mois?: number | null; annee: number }): Observable<RecuperationMeteo> {
    return this.http.post<RecuperationMeteo>(this.url('analyse/meteo-horaire/recuperer/'), body);
  }
  /** Catalogue local des stations ; classé par distance si `ville` est fourni. */
  getStationsMeteo(ville?: string): Observable<CatalogueStations> {
    let params = new HttpParams();
    if (ville) params = params.set('ville', ville);
    return this.http.get<CatalogueStations>(this.url('analyse/meteo-horaire/stations/'), { params });
  }
  /** Rapatrie le catalogue depuis Météo-France (~100 appels : compter une minute). */
  synchroniserStationsMeteo(): Observable<{ detail: string; stations: number; departements_en_echec: string[] }> {
    return this.http.post<{ detail: string; stations: number; departements_en_echec: string[] }>(
      this.url('analyse/meteo-horaire/stations/synchroniser/'), {});
  }
  getIndicateursJournaliers(filters: { ville: string; annee: number; mois?: number | null }): Observable<IndicateursJournaliers> {
    let params = new HttpParams().set('ville', filters.ville).set('annee', String(filters.annee));
    if (filters.mois) params = params.set('mois', String(filters.mois));
    return this.http.get<IndicateursJournaliers>(this.url('analyse/meteo-horaire/indicateurs-journaliers/'), { params });
  }

  // Config indicateurs météo
  getIndicateursMeteo(): Observable<IndicateurMeteoConfig[]> {
    return this.http.get<IndicateurMeteoConfig[]>(this.url('analyse/indicateurs-meteo/'));
  }
  createIndicateurMeteo(data: IndicateurMeteoConfig): Observable<IndicateurMeteoConfig> {
    return this.http.post<IndicateurMeteoConfig>(this.url('analyse/indicateurs-meteo/'), data);
  }
  updateIndicateurMeteo(id: number, data: IndicateurMeteoConfig): Observable<IndicateurMeteoConfig> {
    return this.http.put<IndicateurMeteoConfig>(this.url(`analyse/indicateurs-meteo/${id}/`), data);
  }
  deleteIndicateurMeteo(id: number): Observable<void> {
    return this.http.delete<void>(this.url(`analyse/indicateurs-meteo/${id}/`));
  }

  // Analyse économique — Ventes
  getVentes(filters?: { annee?: number; mois?: number; source?: string }): Observable<VenteAgregee[]> {
    let params = new HttpParams();
    if (filters) {
      for (const [k, v] of Object.entries(filters)) {
        if (v !== undefined && v !== null && v !== '') params = params.set(k, String(v));
      }
    }
    return this.http.get<VenteAgregee[]>(this.url('analyse/ventes/'), { params });
  }
  createVente(data: VenteAgregee): Observable<VenteAgregee> {
    return this.http.post<VenteAgregee>(this.url('analyse/ventes/'), data);
  }
  updateVente(id: number, data: VenteAgregee): Observable<VenteAgregee> {
    return this.http.put<VenteAgregee>(this.url(`analyse/ventes/${id}/`), data);
  }
  deleteVente(id: number): Observable<void> {
    return this.http.delete<void>(this.url(`analyse/ventes/${id}/`));
  }
  recalculerVentesCommandes(body: { annee: number; mois?: number | null }): Observable<{ detail: string; count: number }> {
    return this.http.post<{ detail: string; count: number }>(this.url('analyse/ventes/recalculer-commandes/'), body);
  }
  importerVentesExcel(fichier: File): Observable<{ detail: string; count: number }> {
    const fd = new FormData();
    fd.append('fichier', fichier);
    return this.http.post<{ detail: string; count: number }>(this.url('analyse/ventes/importer-excel/'), fd);
  }
  templateVentesUrl(): string { return this.url('analyse/ventes/template-excel/'); }
  telechargerTemplateVentes(): Observable<Blob> {
    return this.http.get(this.url('analyse/ventes/template-excel/'), { responseType: 'blob' });
  }

  // Analyse économique — Régression
  lancerRegression(body: {
    ville: string; annee: number; mois?: number | null;
    cible: string; categorie?: number | null; source?: string;
  }): Observable<RegressionResultat> {
    return this.http.post<RegressionResultat>(this.url('analyse/ventes/regression/'), body);
  }
}
