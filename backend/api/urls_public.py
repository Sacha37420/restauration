from django.urls import path
from . import views_public

urlpatterns = [
    path('plats/', views_public.public_plats),
    path('commandes/', views_public.public_create_commande),
    path('commandes/<int:commande_id>/', views_public.public_commande_detail),
    path('commandes/<int:commande_id>/lignes/', views_public.public_add_ligne),
    path('commandes/<int:commande_id>/lignes/<int:ligne_id>/', views_public.public_delete_ligne),
    path('commandes/<int:commande_id>/payer/', views_public.public_payer),
    path('commandes/<int:commande_id>/stripe-checkout/', views_public.public_stripe_checkout),
]
