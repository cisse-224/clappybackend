# serializers.py
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from .models import Client, Chauffeur, Vehicule, Course, Paiement, Evaluation, HistoriquePosition, Tarif
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from django.contrib.auth.password_validation import validate_password
import secrets
import string
from rest_framework import viewsets, permissions, status

# ✅ Récupère le modèle utilisateur personnalisé
User = get_user_model()

# ================= TOKEN PERSONNALISÉ =================
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['email'] = user.email

        if hasattr(user, "client"):
            token['role'] = "client"
            token['telephone'] = user.client.telephone
            token['id_client'] = user.client.id
        elif hasattr(user, "chauffeur"):
            token['role'] = "chauffeur"
            token['telephone'] = user.chauffeur.telephone
            token['id_chauffeur'] = user.chauffeur.id
        else:
            token['role'] = "admin" if user.is_staff else "user"

        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['username'] = self.user.username
        data['email'] = self.user.email

        if hasattr(self.user, "client"):
            data['role'] = "client"
            data['telephone'] = self.user.client.telephone
            data['id_client'] = self.user.client.id
        elif hasattr(self.user, "chauffeur"):
            data['role'] = "chauffeur"
            data['telephone'] = self.user.chauffeur.telephone
            data['id_chauffeur'] = self.user.chauffeur.id
        else:
            data['role'] = "admin" if self.user.is_staff else "user"

        return data

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
class UserSerializer(serializers.ModelSerializer):
    chauffeur_id = serializers.SerializerMethodField()
    client_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'telephone',
            'chauffeur_id',
            'client_id'
        ]

    def get_chauffeur_id(self, obj):
        if hasattr(obj, 'chauffeur'):
            return obj.chauffeur.id
        return None

    def get_client_id(self, obj):
        if hasattr(obj, 'client'):
            return obj.client.id
        return None

# ================= CLIENT =================

class ClientCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    nom = serializers.CharField(max_length=100)
    prenom = serializers.CharField(max_length=100)
    telephone = serializers.CharField(max_length=15)
    password = serializers.CharField(
        write_only=True, 
        required=False,
        allow_blank=True,
        min_length=4,
        error_messages={
            'min_length': 'Le mot de passe doit contenir au moins 4 caractères.'
        }
    )
    
    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Un utilisateur avec cet email existe déjà.")
        return value

    def validate_telephone(self, value):
        if Client.objects.filter(telephone=value).exists():
            raise serializers.ValidationError("Un client avec ce téléphone existe déjà.")
        return value

    def validate_password(self, value):
        if value and len(value) < 4:
            raise serializers.ValidationError("Le mot de passe doit contenir au moins 6 caractères.")
        return value

    def generate_random_password(self):
        alphabet = string.ascii_letters + string.digits + "!@#$%"
        password = ''.join(secrets.choice(alphabet) for i in range(12))
        return password

    def create(self, validated_data):
        email = validated_data.get('email')
        nom = validated_data.get('nom')
        prenom = validated_data.get('prenom')
        telephone = validated_data.get('telephone')
        password = validated_data.get('password', None)
        
        # Générer un username unique
        base_username = telephone
        username = base_username
        counter = 1
        
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        
        # Gérer le mot de passe
        if not password:
            password = self.generate_random_password()
            # print(f" Mot de passe généré: {password}")
        
        try:
            # Créer le User
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=prenom,
                last_name=nom
            )
            
            # Créer le Client avec l'utilisateur
            client = Client.objects.create(
                utilisateur=user,
                telephone=telephone
            )
            
            return client
            
        except Exception as e:
            if 'user' in locals():
                user.delete()
            raise serializers.ValidationError(f"Erreur lors de la création: {str(e)}")

    def update(self, instance, validated_data):
        raise NotImplementedError("Update non supporté pour ce serializer")

#  AJOUTER CE ClientSerializer MANQUANT 
class ClientSerializer(serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='client-detail')
    
    # Champs du User lié (en lecture seule)
    nom = serializers.CharField(source='utilisateur.last_name', read_only=True)
    prenom = serializers.CharField(source='utilisateur.first_name', read_only=True)
    email = serializers.EmailField(source='utilisateur.email', read_only=True)
    username = serializers.CharField(source='utilisateur.username', read_only=True)
    
    class Meta:
        model = Client
        fields = [
            'url', 'id', 'utilisateur', 'telephone', 
            'date_creation', 'date_modification',
            'nom', 'prenom', 'email', 'username'
        ]
        read_only_fields = ['date_creation', 'date_modification', 'utilisateur']

# ================= CHAUFFEUR =================
class ChauffeurSerializer(serializers.ModelSerializer):
    utilisateur = UserSerializer(read_only=True)

    class Meta:
        model = Chauffeur
        fields = ['url', 'id', 'utilisateur', 'telephone', 'numero_permis', 
                  'statut', 'est_approuve', 'note_moyenne']
        read_only_fields = ['id', 'note_moyenne']

class ChauffeurCreateSerializer(serializers.ModelSerializer):
    username = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True)
    email = serializers.EmailField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Chauffeur
        fields = ['id', 'username', 'password', 'email', 'telephone', 'numero_permis']

    def create(self, validated_data):
        username = validated_data.pop('username')
        password = validated_data.pop('password')
        email = validated_data.pop('email', '')

        user = User.objects.create_user(username=username, password=password, email=email)
        chauffeur = Chauffeur.objects.create(utilisateur=user, **validated_data)
        return chauffeur

# ================= VÉHICULE =================
class VehiculeSerializer(serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='vehicule-detail')
    chauffeur_details = ChauffeurSerializer(source='chauffeur', read_only=True)

    class Meta:
        model = Vehicule
        fields = [
            'url', 'id', 'chauffeur', 'chauffeur_details',
            'marque', 'modele', 'annee', 'immatriculation',
            'couleur', 'type_vehicule', 'nombre_places', 'date_creation'
        ]
        read_only_fields = ['date_creation']

# ================= COURSE =================
class CourseSerializer(serializers.ModelSerializer):
    client_nom_complet = serializers.CharField(source='client.utilisateur.username', read_only=True)
    chauffeur_nom_complet = serializers.CharField(source='chauffeur.utilisateur.username', read_only=True)
    duree_totale = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            'id',
            "client",
            'client_nom_complet',
            'chauffeur_nom_complet',
            'chauffeur_id',
            'adresse_depart',
            'adresse_destination',
            'type_course',
            'statut',
            'methode_paiement',
            'tarif_estime',
            'tarif_final',
            'duree_totale',
            'latitude_depart',
            'longitude_depart',
            'latitude_destination',
            'longitude_destination',
            'date_reservation',
            'type_vehicule_demande'
        ]
        read_only_fields = ['date_demande']

    def get_duree_totale(self, obj):
        if obj.date_debut and obj.date_fin:
            return (obj.date_fin - obj.date_debut).total_seconds() / 60
        return None


# ================= AUTRES =================
class PaiementSerializer(serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='paiement-detail')
    class Meta:
        model = Paiement
        fields = '__all__'  # ✅ correction

class EvaluationSerializer(serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='evaluation-detail')
    class Meta:
        model = Evaluation
        fields = '__all__'  # ✅ correction

class HistoriquePositionSerializer(serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='historiqueposition-detail')
    class Meta:
        model = HistoriquePosition
        fields = '__all__'  # ✅ correction

class TarifSerializer(serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='tarif-detail')
    class Meta:
        model = Tarif
        fields = '__all__'  # ✅ correctionfrom rest_framework import viewsets, permissions, status
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
from .serializers import (ClientSerializer, ChauffeurSerializer, ChauffeurCreateSerializer, ClientCreateSerializer,
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
from django.db.models import Q

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.views import APIView
from .models import Client, Chauffeur  # Adaptez selon vos modèles

# Service de notification pour les courses
class NotificationService:
    @staticmethod
    def envoyer_notification_course(course_id):
        """Envoyer une notification à tous les chauffeurs du type de véhicule demandé"""
        try:
            course = Course.objects.get(id=course_id)
            type_vehicule_demande = course.type_vehicule_demande
            
            #  Vérifier que channel_layer est disponible
            try:
                channel_layer = get_channel_layer()
                if channel_layer is None:
                    print(" Channel layer non disponible - notification ignorée")
                    return False
                
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
                print(f" Notification envoyée pour course {course_id}")
                return True
                
            except Exception as e:
                print(f" Erreur channel layer: {e} - notification ignorée")
                return False
                
        except Course.DoesNotExist:
            print(f" Course {course_id} non trouvée")
            return False
        except Exception as e:
            print(f" Erreur notification: {e}")
            return False

    @staticmethod
    def notifier_confirmation_course(course_id, chauffeur_id):
        """Notifier que la course a été confirmée"""
        try:
            course = Course.objects.get(id=course_id)
            chauffeur = Chauffeur.objects.get(id=chauffeur_id)
            type_vehicule_demande = course.type_vehicule_demande
            
            #  Vérifier que channel_layer est disponible
            try:
                channel_layer = get_channel_layer()
                if channel_layer is None:
                    print(" Channel layer non disponible - confirmation ignorée")
                    return False
                
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
                print(f" Confirmation notifiée pour course {course_id}")
                return True
                
            except Exception as e:
                print(f" Erreur channel layer confirmation: {e}")
                return False
                
        except (Course.DoesNotExist, Chauffeur.DoesNotExist) as e:
            print(f" Erreur confirmation: {e}")
            return False

from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User
from .serializers import UserSerializer  # Si vous avez un serializer

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    username = request.data.get('username')
    password = request.data.get('password')

    print(f"🔐 Tentative de connexion: {username}")

    user = authenticate(username=username, password=password)

    if not user:
        return Response({
            'status': 'error',
            'message': 'Identifiants invalides',
            'token': None,
            'user': None
        }, status=status.HTTP_401_UNAUTHORIZED)

    refresh = RefreshToken.for_user(user)

    # Déterminer le rôle et l'ID lié
    role = 'inconnu'
    chauffeur_id = None
    client_id = None

    try:
        chauffeur = Chauffeur.objects.get(utilisateur=user)
        role = 'chauffeur'
        chauffeur_id = chauffeur.id
    except Chauffeur.DoesNotExist:
        try:
            client = Client.objects.get(utilisateur=user)
            role = 'client'
            client_id = client.id
        except Client.DoesNotExist:
            role = 'inconnu'

    # Construire la réponse
    user_data = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': role,
        'chauffeur_id': chauffeur_id,
        'client_id': client_id,
    }

    return Response({
        'status': 'success',
        'message': 'Connexion réussie',
        'token': str(refresh.access_token),
        'refresh_token': str(refresh),
        'user': user_data
    }, status=status.HTTP_200_OK)

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
    permission_classes = [AllowAny]  # Rendre l'endpoint public
    queryset = Client.objects.all().select_related('utilisateur')
    
    # ⬅ CORRECTION: Ajouter cette méthode pour utiliser le bon serializer
    def get_serializer_class(self):
        if self.action == 'create':
            return ClientCreateSerializer  # Utiliser le serializer de création
        return ClientSerializer  # Utiliser le serializer normal pour les autres actions

    def create(self, request, *args, **kwargs):
        """
        Création d'un client avec gestion d'erreur améliorée
        """
        print("🎯 Données reçues pour création client:", request.data)
        
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            print("✅ Données valides")
            try:
                client = serializer.save()
                print(f"✅ Client créé: {client.id}, Utilisateur: {client.utilisateur.id}")
                
                # Retourner les données avec le serializer de lecture
                read_serializer = ClientSerializer(client, context={'request': request})
                return Response(read_serializer.data, status=status.HTTP_201_CREATED)
                
            except Exception as e:
                print(f"❌ Erreur lors de la création: {e}")
                return Response(
                    {"detail": f"Erreur lors de la création: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            print("❌ Erreurs de validation:", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
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
    queryset = Course.objects.all().select_related('client_utilisateur', 'chauffeur_utilisateur')
    serializer_class = CourseSerializer
    permission_classes = [permissions.AllowAny]  # ✅ accessible sans token

    def perform_create(self, serializer):
        try:
            course = serializer.save(statut='demandee', date_demande=timezone.now())
            print(f"✅ Course {course.id} créée avec succès")

            try:
                NotificationService.envoyer_notification_course(course.id)
            except Exception as e:
                print(f"⚠ Notification échouée: {e}")
        except Exception as e:
            print(f"❌ Erreur création course: {e}")
            raise

    # ✅ CORRECTEMENT PLACÉ — au même niveau que perform_create
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        # 🚖 Si c’est un chauffeur connecté
        if hasattr(user, 'chauffeur'):
            chauffeur = user.chauffeur

            try:
                vehicule = Vehicule.objects.get(chauffeur=chauffeur)
                type_vehicule = vehicule.type_vehicule

                # ✅ Le chauffeur voit uniquement :
                # - les courses de son type de véhicule
                # - qui sont demandées ou qu’il a acceptées
                queryset = queryset.filter(
                    type_vehicule_demande=type_vehicule
                ).filter(
                    Q(statut='demandee', chauffeur__isnull=True) |
                    Q(chauffeur=chauffeur)
                )

            except Vehicule.DoesNotExist:
                return Course.objects.none()

        else:
            # 👤 Pour client/admin : filtres facultatifs
            statut = self.request.query_params.get('statut')
            if statut:
                queryset = queryset.filter(statut=statut)

            client_id = self.request.query_params.get('client_id')
            if client_id:
                queryset = queryset.filter(client_id=client_id)

            chauffeur_id = self.request.query_params.get('chauffeur_id')
            if chauffeur_id:
                queryset = queryset.filter(chauffeur_id=chauffeur_id)

        return queryset

    @action(detail=True, methods=['post'])
    def accepter(self, request, pk=None):
        """Accepter une course"""
        course = self.get_object()
        chauffeur_id = request.data.get('chauffeur_id')

        if course.statut != 'demandee':
            return Response({'erreur': 'Course déjà acceptée ou terminée'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            chauffeur = Chauffeur.objects.get(id=chauffeur_id)
            course.chauffeur = chauffeur
            course.statut = 'acceptee'
            course.date_acceptation = timezone.now()
            course.save()

            chauffeur.statut = 'en_course'
            chauffeur.save()

            NotificationService.notifier_confirmation_course(course.id, chauffeur.id)

            return Response({'statut': 'Course acceptée'})
        except Chauffeur.DoesNotExist:
            return Response({'erreur': 'Chauffeur non trouvé'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=True, methods=['post'])
    def demarrer(self, request, pk=None):
        """Démarrer une course"""
        course = self.get_object()
        if course.statut != 'acceptee':
            return Response({'erreur': 'Course non acceptée'}, status=status.HTTP_400_BAD_REQUEST)

        course.statut = 'en_cours'
        course.date_debut = timezone.now()
        course.save()

        return Response({'statut': 'Course démarrée'})

    @action(detail=True, methods=['post'])
    def terminer(self, request, pk=None):
        """Terminer une course"""
        course = self.get_object()
        # if course.statut != 'en_cours':
        #     return Response({'erreur': 'Course non en cours'}, status=status.HTTP_400_BAD_REQUEST)

        course.statut = 'terminee'
        course.date_fin = timezone.now()
        course.tarif_final = request.data.get('tarif_final', course.tarif_estime)
        course.save()

        if course.chauffeur:
            course.chauffeur.statut = 'disponible'
            course.chauffeur.save()

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
    queryset = Evaluation.objects.all().select_related('chauffeur_utilisateur', 'client_utilisateur', 'course')
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
            courses.values('chauffeur_id', 'chauffeurutilisateur_username')
            .annotate(revenu_total=Sum('tarif_final'))
            .order_by('-revenu_total')
        )

        if chauffeurs_revenus.exists():
            meilleur = chauffeurs_revenus.first()
            data = {
                "annee": annee_courante,
                "mois": maintenant.strftime("%B"),
                "chauffeur_id": meilleur['chauffeur__id'],
                "chauffeur_nom": meilleur['chauffeur_utilisateur_username'],
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


#Verifier si le numero que le client a entrer pour la creation de son compte existe deja dans la base
@method_decorator(csrf_exempt, name='dispatch')
class CheckPhoneView(APIView):
    permission_classes = [AllowAny]  # Rendre l'endpoint public
    
    def post(self, request):
        telephone = request.data.get('telephone', '').strip()
        
        if not telephone:
            return JsonResponse({
                'error': 'Le numéro de téléphone est requis'
            }, status=400)
        
        # Vérifier si le téléphone existe dans Client
        client_exists = Client.objects.filter(telephone=telephone).exists()
        
        # Vérifier si le téléphone existe dans Chauffeur (si applicable)
        chauffeur_exists = Chauffeur.objects.filter(telephone=telephone).exists()
        
        exists = client_exists or chauffeur_exists
        
        return JsonResponse({
            'exists': exists,
            'telephone': telephone,
            'message': 'Numéro déjà utilisé' if exists else 'Numéro disponible'
        })
    
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

# ================= CHANGEMENT DE MOT DE PASSE =================
class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("L'ancien mot de passe est incorrect.")
        return value

    def validate(self, data):
        if data['old_password'] == data['new_password']:
            raise serializers.ValidationError("Le nouveau mot de passe doit être différent de l'ancien.")
        return data