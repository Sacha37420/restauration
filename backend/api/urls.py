from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CategoriePlatViewSet, SousCategoriePlatViewSet,
    FournisseurViewSet, UniteViewSet, IngredientViewSet,
    RecetteViewSet, PlatViewSet, StockPlatViewSet,
    TableRestaurantViewSet, CompteClientViewSet, EmployeViewSet,
    CanalCommandeViewSet, StatutCommandeViewSet, StatutPaiementViewSet,
    CommandeViewSet, PaiementViewSet, PlageTravailViewSet, MouvementStockViewSet,
)
from .views_stripe import ConfigurationStripeView, CreerSessionCheckoutView, WebhookStripeView
from .views_email import ConfigurationEmailView, TestEmailView
from .views_integrations import ConfigurationAgentEvenementsView, ConfigurationMeteoView
from .views_analyse import EvenementViewSet

router = DefaultRouter()
router.register('categories-plat', CategoriePlatViewSet)
router.register('sous-categories-plat', SousCategoriePlatViewSet)
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
router.register('analyse/evenements', EvenementViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('stripe/configuration/', ConfigurationStripeView.as_view(), name='stripe-configuration'),
    path('stripe/checkout/', CreerSessionCheckoutView.as_view(), name='stripe-checkout'),
    path('stripe/webhook/', WebhookStripeView.as_view(), name='stripe-webhook'),
    path('email/configuration/', ConfigurationEmailView.as_view(), name='email-configuration'),
    path('email/test/', TestEmailView.as_view(), name='email-test'),
    path('agent-evenements/configuration/', ConfigurationAgentEvenementsView.as_view(), name='agent-evenements-configuration'),
    path('meteo/configuration/', ConfigurationMeteoView.as_view(), name='meteo-configuration'),
]
