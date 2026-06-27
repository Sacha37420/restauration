import { Routes } from '@angular/router';

export const routes: Routes = [
  {
    path: '',
    loadComponent: () => import('./pages/home/home.component').then(m => m.HomeComponent),
  },
  {
    path: 'fournisseurs',
    loadComponent: () => import('./pages/fournisseurs/fournisseurs.component').then(m => m.FournisseursComponent),
  },
  {
    path: 'ingredients',
    loadComponent: () => import('./pages/ingredients/ingredients.component').then(m => m.IngredientsComponent),
  },
  {
    path: 'recettes',
    loadComponent: () => import('./pages/recettes/recettes.component').then(m => m.RecettesComponent),
  },
  {
    path: 'plats',
    loadComponent: () => import('./pages/plats/plats.component').then(m => m.PlatsComponent),
  },
  {
    path: 'categories-plat',
    loadComponent: () => import('./pages/categories-plat/categories-plat.component').then(m => m.CategoriesPlatComponent),
  },
  {
    path: 'commandes',
    loadComponent: () => import('./pages/commandes/commandes.component').then(m => m.CommandesComponent),
  },
  {
    path: 'planning',
    loadComponent: () => import('./pages/planning/planning.component').then(m => m.PlanningComponent),
  },
  {
    path: 'unites',
    loadComponent: () => import('./pages/unites/unites.component').then(m => m.UnitesComponent),
  },
  {
    path: 'plan-tables',
    loadComponent: () => import('./pages/plan-tables/plan-tables.component').then(m => m.PlanTablesComponent),
  },
  {
    path: 'commander',
    loadComponent: () => import('./pages/commande-publique/commande-publique.component').then(m => m.CommandePubliqueComponent),
  },
  {
    path: 'parametres',
    loadComponent: () => import('./pages/parametres/parametres.component').then(m => m.ParametresComponent),
  },
  {
    path: 'utilisateurs',
    loadComponent: () => import('./pages/utilisateurs/utilisateurs.component').then(m => m.UtilisateursComponent),
  },
  {
    path: 'analyse/evenements',
    loadComponent: () => import('./pages/analyse-evenements/analyse-evenements.component').then(m => m.AnalyseEvenementsComponent),
  },
  {
    path: 'analyse/meteo',
    loadComponent: () => import('./pages/analyse-meteo/analyse-meteo.component').then(m => m.AnalyseMeteoComponent),
  },
  {
    path: 'analyse/ventes',
    loadComponent: () => import('./pages/analyse-ventes/analyse-ventes.component').then(m => m.AnalyseVentesComponent),
  },
  {
    path: 'analyse/regression',
    loadComponent: () => import('./pages/analyse-regression/analyse-regression.component').then(m => m.AnalyseRegressionComponent),
  },
  { path: '**', redirectTo: '' },
];
