from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Avg, Sum
from django.utils import timezone
from datetime import timedelta
from channels.generic.websocket import AsyncWebsocketConsumer
import json
from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer
from .models import Client, Chauffeur, Vehicule, Course, Paiement, Evaluation, HistoriquePosition, Tarif
from .serializers import (ClientSerializer, ChauffeurSerializer, ChauffeurCreateSerializer,
                          VehiculeSerializer, CourseSerializer, PaiementSerializer,
                          EvaluationSerializer, HistoriquePositionSerializer, TarifSerializer, UserSerializer)
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.permissions import IsAdminUser, AllowAny
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView

# Service de notification pour les courses
class NotificationService:
    @staticmethod
    def envoyer_notification_course(course_id):
        """Envoyer une notification à tous les chauffeurs du type de véhicule demandé"""
        try:
            course = Course.objects.get(id=course_id)
            type_vehicule_demande = course.type_vehicule_demande
            
            channel_layer = get_channel_layer()
            
            # Envoyer la notification à tous les chauffeurs du type de véhicule demandé
            async_to_sync(channel_layer.group_send)(
                f"chauffeurs_{type_vehicule_demande}",
                {
                    "type": "send_course_alert",
                    "message": "Nouvelle course disponible!",
                    "course_id": course.id,
                    "depart": course.adresse_depart,
                    "destination": course.adresse_destination,
                    "tarif_estime": str(course.tarif_estime),
                    "type_vehicule": type_vehicule_demande
                }
            )
            
            return True
        except Course.DoesNotExist:
            return False

    @staticmethod
    def notifier_confirmation_course(course_id, chauffeur_id):
        """Notifier que la course a été confirmée"""
        try:
            course = Course.objects.get(id=course_id)
            chauffeur = Chauffeur.objects.get(id=chauffeur_id)
            type_vehicule_demande = course.type_vehicule_demande
            
            channel_layer = get_channel_layer()
            
            # Notifier tous les chauffeurs que la course a été prise
            async_to_sync(channel_layer.group_send)(
                f"chauffeurs_{type_vehicule_demande}",
                {
                    "type": "course_confirmed",
                    "message": "Cette course a été confirmée par un autre chauffeur",
                    "course_id": course.id,
                    "chauffeur_name": str(chauffeur)
                }
            )
            
            return True
        except (Course.DoesNotExist, Chauffeur.DoesNotExist):
            return False

@api_view(['POST'])
def login_view(request):
    username = request.data.get('username')
    password = request.data.get('password')
    user = authenticate(username=username, password=password)
    if user:
        # Générer un token (SimpleJWT ou autre)
        return Response({'token': 'votre_token'})
    return Response({'detail': 'Identifiants invalides'}, status=status.HTTP_401_UNAUTHORIZED)

class LogoutRefreshView(APIView):
    """
    Blacklist the provided refresh token so it cannot be used again.
    Accepts { "refresh": "<refresh_token>" } in POST body.
    """
    permission_classes = (AllowAny,)  # AllowAny is OK because we validate the token itself.
    def post(self, request, *args, **kwargs):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'detail': 'Refresh token is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({'detail': 'Refresh token blacklisted.'}, status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class ClientViewSet(viewsets.ModelViewSet):
    queryset = Client.objects.all().select_related('utilisateur')
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=True, methods=['get'])
    def courses(self, request, pk=None):
        """Liste toutes les courses d'un client"""
        client = self.get_object()
        courses = Course.objects.filter(client=client)
        serializer = CourseSerializer(courses, many=True, context={'request': request})
        return Response(serializer.data)

User = get_user_model()

class ChauffeurViewSet(viewsets.ModelViewSet):
    queryset = Chauffeur.objects.all().select_related('utilisateur')
    permission_classes = [IsAdminUser]

    def get_serializer_class(self):
        # Lors de la création, on utilise un serializer spécial qui crée aussi l'utilisateur
        if self.action == 'create':
            return ChauffeurCreateSerializer
        return ChauffeurSerializer

    def create(self, request, *args, **kwargs):
        """
        Création d'un chauffeur + compte utilisateur lié
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        chauffeur = serializer.save()
        return Response(
            ChauffeurSerializer(chauffeur, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['get'])
    def courses(self, request, pk=None):
        """Liste toutes les courses d'un chauffeur"""
        chauffeur = self.get_object()
        courses = Course.objects.filter(chauffeur=chauffeur)
        serializer = CourseSerializer(courses, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def statistiques(self, request, pk=None):
        """Statistiques détaillées d'un chauffeur"""
        chauffeur = self.get_object()
        
        courses_total = Course.objects.filter(chauffeur=chauffeur).count()
        courses_mois = Course.objects.filter(
            chauffeur=chauffeur,
            date_demande__month=timezone.now().month
        ).count()
        revenu_total = Paiement.objects.filter(
            course__chauffeur=chauffeur,
            statut_paiement='paye'
        ).aggregate(total=Sum('montant'))['total'] or 0
        note_moyenne = Evaluation.objects.filter(
            chauffeur=chauffeur
        ).aggregate(moyenne=Avg('note_chauffeur'))['moyenne'] or 0
        
        return Response({
            'courses_total': courses_total,
            'courses_mois': courses_mois,
            'revenu_total': revenu_total,
            'note_moyenne': round(note_moyenne, 2)
        })
    
    @action(detail=True, methods=['post'])
    def changer_statut(self, request, pk=None):
        """Changer le statut d'un chauffeur"""
        chauffeur = self.get_object()
        nouveau_statut = request.data.get('statut')
        
        if nouveau_statut in dict(Chauffeur.STATUT_CHOIX):
            chauffeur.statut = nouveau_statut
            chauffeur.save()
            return Response({'statut': 'Statut mis à jour'})
        return Response({'erreur': 'Statut invalide'}, status=status.HTTP_400_BAD_REQUEST)

class ChauffeurConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Le chauffeur rejoint un groupe basé sur son type de véhicule
        user = self.scope["user"]
        if user.is_authenticated and hasattr(user, 'chauffeur'):
            try:
                chauffeur = await sync_to_async(Chauffeur.objects.get)(utilisateur=user)
                vehicule = await sync_to_async(Vehicule.objects.get)(chauffeur=chauffeur)
                self.type_vehicule = vehicule.type_vehicule
                self.group_name = f"chauffeurs_{self.type_vehicule}"
                
                await self.channel_layer.group_add(
                    self.group_name,
                    self.channel_name
                )
                await self.accept()
                
                # Envoyer un message de connexion réussie
                await self.send(text_data=json.dumps({
                    'type': 'connection_success',
                    'message': f'Connecté au groupe {self.type_vehicule}'
                }))
            except (Chauffeur.DoesNotExist, Vehicule.DoesNotExist):
                await self.close()
        else:
            await self.close()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_type = text_data_json.get('type')
        
        if message_type == 'confirm_course':
            course_id = text_data_json.get('course_id')
            chauffeur_id = text_data_json.get('chauffeur_id')
            
            # Traiter la confirmation de course
            await self.confirm_course(course_id, chauffeur_id)

    async def send_course_alert(self, event):
        """Envoyer une alerte de nouvelle course à tous les chauffeurs du groupe"""
        await self.send(text_data=json.dumps({
            "type": "new_course",
            "message": event['message'],
            "course_id": event['course_id'],
            "depart": event['depart'],
            "destination": event['destination'],
            "tarif_estime": str(event['tarif_estime']),
            "type_vehicule": event['type_vehicule']
        }))

    async def course_confirmed(self, event):
        """Notifier qu'une course a été confirmée par un chauffeur"""
        await self.send(text_data=json.dumps({
            "type": "course_confirmed",
            "message": event['message'],
            "course_id": event['course_id'],
            "chauffeur_name": event['chauffeur_name']
        }))

    @sync_to_async
    def confirm_course(self, course_id, chauffeur_id):
        """Confirmer une course (méthode synchrone wrappée)"""
        from .models import Course, Chauffeur
        try:
            course = Course.objects.get(id=course_id)
            chauffeur = Chauffeur.objects.get(id=chauffeur_id)
            
            # Vérifier si la course est toujours disponible
            if course.statut == 'demandee':
                course.chauffeur = chauffeur
                course.statut = 'acceptee'
                course.date_acceptation = timezone.now()
                course.save()
                
                # Mettre à jour le statut du chauffeur
                chauffeur.statut = 'en_course'
                chauffeur.save()
                
                # Notifier les autres chauffeurs
                NotificationService.notifier_confirmation_course(course.id, chauffeur.id)
                return True
            return False
        except (Course.DoesNotExist, Chauffeur.DoesNotExist):
            return False

class VehiculeViewSet(viewsets.ModelViewSet):
    queryset = Vehicule.objects.all().select_related('chauffeur__utilisateur')
    serializer_class = VehiculeSerializer
    permission_classes = [permissions.IsAuthenticated]

class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.all().select_related('client__utilisateur', 'chauffeur__utilisateur')
    serializer_class = CourseSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def perform_create(self, serializer):
        course = serializer.save(statut='demandee', date_demande=timezone.now())
        
        # Envoyer la notification à tous les chauffeurs du type de véhicule demandé
        NotificationService.envoyer_notification_course(course.id)

    def get_queryset(self):
        """Filtrage personnalisé des courses"""
        queryset = super().get_queryset()
        
        # Filtre par statut
        statut = self.request.query_params.get('statut')
        if statut:
            queryset = queryset.filter(statut=statut)
        
        # Filtre par client
        client_id = self.request.query_params.get('client_id')
        if client_id:
            queryset = queryset.filter(client_id=client_id)
        
        # Filtre par chauffeur
        chauffeur_id = self.request.query_params.get('chauffeur_id')
        if chauffeur_id:
            queryset = queryset.filter(chauffeur_id=chauffeur_id)
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def accepter(self, request, pk=None):
        """Accepter une course (pour l'admin ou système manuel)"""
        course = self.get_object()
        chauffeur_id = request.data.get('chauffeur_id')
        
        if course.statut != 'demandee':
            return Response(
                {'erreur': 'Course déjà acceptée ou terminée'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            chauffeur = Chauffeur.objects.get(id=chauffeur_id)
            course.chauffeur = chauffeur
            course.statut = 'acceptee'
            course.date_acceptation = timezone.now()
            course.save()
            
            # Mettre à jour le statut du chauffeur
            chauffeur.statut = 'en_course'
            chauffeur.save()
            
            # Notifier les autres chauffeurs
            NotificationService.notifier_confirmation_course(course.id, chauffeur.id)
            
            return Response({'statut': 'Course acceptée'})
            
        except Chauffeur.DoesNotExist:
            return Response(
                {'erreur': 'Chauffeur non trouvé'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['post'])
    def confirmer_par_chauffeur(self, request, pk=None):
        """Un chauffeur confirme une course via WebSocket"""
        course = self.get_object()
        chauffeur_id = request.data.get('chauffeur_id')
        
        if not chauffeur_id:
            return Response(
                {'erreur': 'ID chauffeur requis'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if course.statut != 'demandee':
            return Response(
                {'erreur': 'Course déjà acceptée ou terminée'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            chauffeur = Chauffeur.objects.get(id=chauffeur_id)
            
            # Vérifier que le chauffeur a le bon type de véhicule
            try:
                vehicule_chauffeur = Vehicule.objects.get(chauffeur=chauffeur)
                if vehicule_chauffeur.type_vehicule != course.type_vehicule_demande:
                    return Response(
                        {'erreur': 'Type de véhicule incompatible'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except Vehicule.DoesNotExist:
                return Response(
                    {'erreur': 'Chauffeur sans véhicule'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Confirmer la course
            course.chauffeur = chauffeur
            course.statut = 'acceptee'
            course.date_acceptation = timezone.now()
            course.save()
            
            # Mettre à jour le statut du chauffeur
            chauffeur.statut = 'en_course'
            chauffeur.save()
            
            # Notifier les autres chauffeurs que la course est prise
            NotificationService.notifier_confirmation_course(course.id, chauffeur.id)
            
            return Response({
                'statut': 'Course confirmée',
                'course_id': course.id,
                'chauffeur_id': chauffeur.id
            })
            
        except Chauffeur.DoesNotExist:
            return Response(
                {'erreur': 'Chauffeur non trouvé'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['post'])
    def demarrer(self, request, pk=None):
        """Démarrer une course"""
        course = self.get_object()
        
        if course.statut != 'acceptee':
            return Response(
                {'erreur': 'Course non acceptée'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        course.statut = 'en_cours'
        course.date_debut = timezone.now()
        course.save()
        
        return Response({'statut': 'Course démarrée'})
    
    @action(detail=True, methods=['post'])
    def terminer(self, request, pk=None):
        """Terminer une course"""
        course = self.get_object()
        
        if course.statut != 'en_cours':
            return Response(
                {'erreur': 'Course non en cours'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        course.statut = 'terminee'
        course.date_fin = timezone.now()
        course.tarif_final = request.data.get('tarif_final', course.tarif_estime)
        course.save()
        
        # Libérer le chauffeur
        if course.chauffeur:
            course.chauffeur.statut = 'disponible'
            course.chauffeur.save()
        
        # Créer le paiement associé
        Paiement.objects.create(
            course=course,
            montant=course.tarif_final,
            statut_paiement='en_attente'
        )
        
        return Response({'statut': 'Course terminée'})
    
    @action(detail=False, methods=['get'])
    def en_cours(self, request):
        """Liste des courses en cours"""
        courses = Course.objects.filter(statut='en_cours')
        serializer = self.get_serializer(courses, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def disponibles(self, request):
        """Liste des courses disponibles (non acceptées)"""
        courses = Course.objects.filter(statut='demandee')
        serializer = self.get_serializer(courses, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def statistiques(self, request):
        """Statistiques générales des courses"""
        aujourd_hui = timezone.now().date()
        debut_mois = aujourd_hui.replace(day=1)
        
        stats = {
            'total_courses': Course.objects.count(),
            'courses_aujourdhui': Course.objects.filter(date_demande__date=aujourd_hui).count(),
            'courses_mois': Course.objects.filter(date_demande__date__gte=debut_mois).count(),
            'chiffre_affaires': Paiement.objects.filter(
                statut_paiement='paye'
            ).aggregate(total=Sum('montant'))['total'] or 0,
            'taux_completion': Course.objects.filter(statut='terminee').count() / max(Course.objects.count(), 1) * 100
        }
        
        return Response(stats)

class PaiementViewSet(viewsets.ModelViewSet):
    queryset = Paiement.objects.all().select_related('course')
    serializer_class = PaiementSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=True, methods=['post'])
    def confirmer(self, request, pk=None):
        """Confirmer un paiement"""
        paiement = self.get_object()
        
        if paiement.statut_paiement == 'paye':
            return Response(
                {'erreur': 'Paiement déjà confirmé'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        paiement.statut_paiement = 'paye'
        paiement.date_confirmation = timezone.now()
        paiement.identifiant_transaction = request.data.get('transaction_id', '')
        paiement.save()
        
        return Response({'statut': 'Paiement confirmé'})

class EvaluationViewSet(viewsets.ModelViewSet):
    queryset = Evaluation.objects.all().select_related('chauffeur__utilisateur', 'client__utilisateur', 'course')
    serializer_class = EvaluationSerializer
    permission_classes = [permissions.IsAuthenticated]

class HistoriquePositionViewSet(viewsets.ModelViewSet):
    queryset = HistoriquePosition.objects.all().select_related('chauffeur__utilisateur')
    serializer_class = HistoriquePositionSerializer
    permission_classes = [permissions.IsAuthenticated]

class TarifViewSet(viewsets.ModelViewSet):
    queryset = Tarif.objects.filter(est_actif=True)
    serializer_class = TarifSerializer
    permission_classes = [permissions.IsAuthenticated]

class RevenuMensuelView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        # Obtenir la date actuelle
        maintenant = timezone.now()
        mois_courant = maintenant.month
        annee_courante = maintenant.year

        # Filtrer uniquement les courses terminées ce mois-ci
        courses = Course.objects.filter(
            statut='terminee',
            date_fin__year=annee_courante,
            date_fin__month=mois_courant
        )

        # Calcul du revenu total du mois
        revenu_total = courses.aggregate(total=Sum('tarif_final'))['total'] or 0

        # Calcul du nombre de courses terminées
        nombre_courses = courses.count()

        # Préparer les données de réponse
        data = {
            "annee": annee_courante,
            "mois": maintenant.strftime("%B"),
            "revenu_total": float(revenu_total),
            "nombre_courses": nombre_courses
        }

        return Response(data)
    
class RevenuJournalierView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        maintenant = timezone.now()
        jour_courant = maintenant.day
        mois_courant = maintenant.month
        annee_courante = maintenant.year

        # Courses terminées aujourd'hui
        courses = Course.objects.filter(
            statut='terminee',
            date_fin__year=annee_courante,
            date_fin__month=mois_courant,
            date_fin__day=jour_courant
        )

        revenu_total = courses.aggregate(total=Sum('tarif_final'))['total'] or 0
        nombre_courses = courses.count()

        data = {
            "annee": annee_courante,
            "mois": maintenant.strftime("%B"),
            "jour": jour_courant,
            "revenu_total": float(revenu_total),
            "nombre_courses": nombre_courses
        }

        return Response(data)

class UserProfileView(APIView):
    """
    Retourne les informations de l'utilisateur connecté
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

class ChangePasswordView(APIView):
    """
    Permet à un utilisateur connecté de changer son mot de passe
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user
        ancien_mot_de_passe = request.data.get("ancien_mot_de_passe")
        nouveau_mot_de_passe = request.data.get("nouveau_mot_de_passe")
        confirmation = request.data.get("confirmation")

        # Vérifier que tous les champs sont présents
        if not ancien_mot_de_passe or not nouveau_mot_de_passe or not confirmation:
            return Response(
                {"detail": "Tous les champs sont requis."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Vérifier que l'ancien mot de passe est correct
        if not user.check_password(ancien_mot_de_passe):
            return Response(
                {"detail": "Ancien mot de passe incorrect."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Vérifier la confirmation
        if nouveau_mot_de_passe != confirmation:
            return Response(
                {"detail": "Les mots de passe ne correspondent pas."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Changer le mot de passe
        user.set_password(nouveau_mot_de_passe)
        user.save()

        return Response(
            {"detail": "Mot de passe modifié avec succès."},
            status=status.HTTP_200_OK
        )
    
class MeilleurChauffeurDuMoisView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        maintenant = timezone.now()
        mois_courant = maintenant.month
        annee_courante = maintenant.year

        # On filtre les courses terminées ce mois
        courses = Course.objects.filter(
            statut='terminee',
            date_fin__year=annee_courante,
            date_fin__month=mois_courant,
            chauffeur__isnull=False
        )

        # On groupe par chauffeur et on calcule le revenu total
        chauffeurs_revenus = (
            courses.values('chauffeur__id', 'chauffeur__utilisateur__username')
            .annotate(revenu_total=Sum('tarif_final'))
            .order_by('-revenu_total')
        )

        if chauffeurs_revenus.exists():
            meilleur = chauffeurs_revenus.first()
            data = {
                "annee": annee_courante,
                "mois": maintenant.strftime("%B"),
                "chauffeur_id": meilleur['chauffeur__id'],
                "chauffeur_nom": meilleur['chauffeur__utilisateur__username'],
                "revenu_total": float(meilleur['revenu_total']),
            }
        else:
            data = {
                "message": "Aucun chauffeur trouvé pour ce mois."
            }

        return Response(data)

# Vue pour les chauffeurs disponibles par type de véhicule
class ChauffeursDisponiblesView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        type_vehicule = request.query_params.get('type_vehicule')
        if not type_vehicule:
            return Response(
                {"erreur": "Le paramètre type_vehicule est requis"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Récupérer les chauffeurs disponibles avec le type de véhicule demandé
        chauffeurs = Chauffeur.objects.filter(
            statut='disponible',
            vehicule__type_vehicule=type_vehicule
        ).select_related('utilisateur', 'vehicule')

        data = []
        for chauffeur in chauffeurs:
            data.append({
                'id': chauffeur.id,
                'nom': str(chauffeur),
                'telephone': chauffeur.telephone,
                'note_moyenne': float(chauffeur.note_moyenne),
                'vehicule': {
                    'marque': chauffeur.vehicule.marque,
                    'modele': chauffeur.vehicule.modele,
                    'immatriculation': chauffeur.vehicule.immatriculation
                }
            })

        return Response(data)

# Vue pour tester les notifications
class TestNotificationView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        course_id = request.data.get('course_id')
        if not course_id:
            return Response(
                {"erreur": "L'ID de la course est requis"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Tester l'envoi de notification
        success = NotificationService.envoyer_notification_course(course_id)
        
        if success:
            return Response({"message": "Notification envoyée avec succès"})
        else:
            return Response(
                {"erreur": "Erreur lors de l'envoi de la notification"},
                status=status.HTTP_400_BAD_REQUEST
            )