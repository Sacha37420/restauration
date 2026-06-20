from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FournisseurViewSet, UniteViewSet, IngredientViewSet,
    RecetteViewSet, PlatViewSet, StockPlatViewSet,
    TableRestaurantViewSet, CompteClientViewSet, EmployeViewSet,
    CanalCommandeViewSet, StatutCommandeViewSet, StatutPaiementViewSet,
    CommandeViewSet, PaiementViewSet, PlageTravailViewSet, MouvementStockViewSet,
)

router = DefaultRouter()
router.register('fournisseurs', FournisseurViewSet)
router.register('unites', UniteViewSet)
router.register('ingredients', IngredientViewSet)
router.register('recettes', RecetteViewSet)
router.register('plats', PlatViewSet)
router.register('stocks-plat', StockPlatViewSet)
router.register('tables', TableRestaurantViewSet)
router.register('comptes-clients', CompteClientViewSet)
router.register('employes', EmployeViewSet)
router.register('canaux-commande', CanalCommandeViewSet)
router.register('statuts-commande', StatutCommandeViewSet)
router.register('statuts-paiement', StatutPaiementViewSet)
router.register('commandes', CommandeViewSet)
router.register('paiements', PaiementViewSet)
router.register('plages-travail', PlageTravailViewSet)
router.register('mouvements-stock', MouvementStockViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
