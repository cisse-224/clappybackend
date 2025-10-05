from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

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
]