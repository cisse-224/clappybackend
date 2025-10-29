from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView


from .views import LogoutRefreshView,UserProfileView, MeilleurChauffeurDuMoisView, RevenuJournalierView,RevenuMensuelView,ChangePasswordView, CheckPhoneView

from . import views

router = DefaultRouter()
router.register(r'clients', views.ClientViewSet)
router.register(r'chauffeurs', views.ChauffeurViewSet)
router.register(r'vehicules', views.VehiculeViewSet)
router.register(r'courses', views.CourseViewSet)
router.register(r'paiements', views.PaiementViewSet)
router.register(r'evaluations', views.EvaluationViewSet)
router.register(r'historique_positions', views.HistoriquePositionViewSet)
router.register(r'tarifs', views.TarifViewSet)


urlpatterns = [
    path('', include(router.urls)),
    path('login/', views.login_view, name='login'),
    path("token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutRefreshView.as_view(), name="token_logout"),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('me/', UserProfileView.as_view(), name='user-profile'),
    path('check-phone/', CheckPhoneView.as_view(), name='check-phone'),  
    # Tes vues de statistiques
    path('revenu-mensuel/', RevenuMensuelView.as_view(), name='revenu-mensuel'),
    path('revenu-journalier/', RevenuJournalierView.as_view(), name='revenu-journalier'),
    path('meilleur-chauffeur/', MeilleurChauffeurDuMoisView.as_view(), name='meilleur-chauffeur'),
]
  