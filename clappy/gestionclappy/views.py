import logging
import threading 
import http.client
from django.conf import settings
import phonenumbers
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action, permission_classes, api_view
from rest_framework.response import Response
from django.db.models import Count, Avg, Sum
from django.utils import timezone
from datetime import timedelta
from channels.generic.websocket import AsyncWebsocketConsumer
import json
from rest_framework.pagination import PageNumberPagination
from asgiref.sync import async_to_sync, sync_to_async
from channels.layers import get_channel_layer
from .models import Client, Chauffeur, Vehicule, Course, Paiement, Evaluation, HistoriquePosition, Tarif
from .serializers import (ClientSerializer, ChauffeurSerializer, ChauffeurCreateSerializer, ClientCreateSerializer,
                          VehiculeSerializer, CourseSerializer, PaiementSerializer,
                          EvaluationSerializer, HistoriquePositionSerializer, TarifSerializer, UserSerializer)
from django.contrib.auth import authenticate
from rest_framework.permissions import IsAdminUser, AllowAny
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from django.db.models import Q

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .models import Client, Chauffeur

# Configuration du logging
logger = logging.getLogger(__name__)

# Service SMS pour les notifications de réservation
class SMSService:
    @staticmethod
    def envoyer_sms_chauffeurs(course_id):
        """Envoyer un SMS à tous les chauffeurs du type de véhicule demandé"""
        try:
            course = Course.objects.get(id=course_id)
            type_vehicule_demande = course.type_vehicule_demande
            
            print(f"🔍 Recherche chauffeurs pour type véhicule: {type_vehicule_demande}")
            
            # Récupérer tous les chauffeurs avec le type de véhicule demandé
            chauffeurs = Chauffeur.objects.filter(
                vehicule__type_vehicule=type_vehicule_demande,
                statut='disponible'
            ).select_related('vehicule', 'utilisateur')
            
            print(f"🔍 {chauffeurs.count()} chauffeurs trouvés pour type {type_vehicule_demande}")
            
            message_chauffeur = (
                f"🚗 NOUVELLE RÉSERVATION DISPONIBLE!\n"
                f"Type véhicule: {type_vehicule_demande}\n"
                f"Départ: {course.adresse_depart}\n"
                f"Destination: {course.adresse_destination}\n"
                f"Tarif estimé: {course.tarif_estime} GNF\n"
                f"Connectez-vous pour accepter la course."
            )
            
            sms_envoyes = 0
            # Envoyer SMS à chaque chauffeur
            for chauffeur in chauffeurs:
                if chauffeur.telephone:
                    print(f"📱 Envoi SMS au chauffeur {chauffeur.id}: {chauffeur.telephone}")
                    threading.Thread(
                        target=SMSService._envoyer_sms,
                        args=(chauffeur.telephone, message_chauffeur),
                        daemon=True
                    ).start()
                    sms_envoyes += 1
                    print(f"📱 SMS réservation programmé pour chauffeur {chauffeur.telephone}")
                else:
                    print(f"⚠ Chauffeur {chauffeur.id} n'a pas de numéro de téléphone")
            
            print(f"✅ {sms_envoyes} SMS programmés pour les chauffeurs")
            return sms_envoyes > 0
            
        except Course.DoesNotExist:
            print(f"❌ Course {course_id} non trouvée pour SMS chauffeurs")
            return False
        except Exception as e:
            print(f"❌ Erreur SMS chauffeurs: {e}")
            import traceback
            traceback.print_exc()
            return False

    @staticmethod
    def envoyer_sms_confirmation_client(course_id):
        """Envoyer un SMS de confirmation au client quand la course est confirmée"""
        try:
            course = Course.objects.get(id=course_id)
            client = course.client
            chauffeur = course.chauffeur
            
            if not client or not chauffeur:
                print(f"❌ Client ou chauffeur manquant pour course {course_id}")
                return False
            
            # Obtenir le nom du chauffeur
            nom_chauffeur = chauffeur.utilisateur.get_full_name() or chauffeur.utilisateur.username
            
            message_client = (
                f"✅ VOTRE RÉSERVATION EST CONFIRMÉE!\n"
                f"Chauffeur: {nom_chauffeur}\n"
                f"Véhicule: {chauffeur.vehicule.marque} {chauffeur.vehicule.modele}\n"
                f"Immatriculation: {chauffeur.vehicule.immatriculation}\n"
                f"Téléphone chauffeur: {chauffeur.telephone}\n"
                f"Merci pour votre confiance!"
            )
            
            if client.telephone:
                print(f"📱 Envoi SMS confirmation au client {client.telephone}")
                threading.Thread(
                    target=SMSService._envoyer_sms,
                    args=(client.telephone, message_client),
                    daemon=True
                ).start()
                print(f"📱 SMS confirmation envoyé au client {client.telephone}")
                return True
            else:
                print(f"⚠ Client {client.id} n'a pas de numéro de téléphone")
                return False
                
        except Course.DoesNotExist:
            print(f"❌ Course {course_id} non trouvée pour SMS client")
            return False
        except Exception as e:
            print(f"❌ Erreur SMS client: {e}")
            import traceback
            traceback.print_exc()
            return False

    @staticmethod
    def _envoyer_sms(telephone, message):
        """Méthode interne pour envoyer un SMS via NimbaSMS"""
        try:
            if not telephone:
                print("❌ Aucun numéro de téléphone fourni")
                return False

            print(f"📱 Tentative d'envoi SMS à: {telephone}")
            print(f"📱 Message: {message}")

            # Validation et formatage international
            try:
                parsed = phonenumbers.parse(telephone, "GN")
                if not phonenumbers.is_valid_number(parsed):
                    logger.error(f"Numéro invalide: {telephone}")
                    print(f"❌ Numéro invalide: {telephone}")
                    return False
                phone_e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                print(f"📱 Numéro formaté: {phone_e164}")
            except phonenumbers.NumberParseException as e:
                logger.error(f"Erreur de parsing du numéro: {telephone} - {e}")
                print(f"❌ Erreur parsing numéro: {e}")
                return False

            # Vérifier que la clé API est configurée
            if not hasattr(settings, 'NIMBASMS_API_KEY') or not settings.NIMBASMS_API_KEY:
                print("❌ Clé API NimbaSMS non configurée")
                return False

            # Configuration requête
            conn = http.client.HTTPSConnection("api.nimbasms.com", timeout=30)
            headers = {
                "Authorization": settings.NIMBASMS_API_KEY.strip(),
                "Content-Type": "application/json",
                "Accept": "application/json"
            }

            payload = {
                "to": [phone_e164],
                "sender_name": getattr(settings, 'NIMBASMS_SENDER_NAME', 'CLAPPY'),
                "message": message
            }

            print(f"📱 Payload SMS: {payload}")

            # Envoi
            conn.request("POST", "/v1/messages", body=json.dumps(payload), headers=headers)
            response = conn.getresponse()
            response_body = response.read().decode()
            
            logger.info(f"Réponse NimbaSMS: {response.status} {response_body}")
            print(f"📱 Réponse NimbaSMS: {response.status} - {response_body}")
            
            if response.status == 201:
                logger.info(f"SMS envoyé avec succès à {telephone}")
                print(f"✅ SMS envoyé avec succès à {telephone}")
                return True
            else:
                logger.error(f"Erreur SMS {response.status}: {response_body}")
                print(f"❌ Erreur SMS {response.status}: {response_body}")
                return False

        except Exception as e:
            logger.error(f"Erreur envoi SMS: {str(e)}", exc_info=True)
            print(f"❌ Exception envoi SMS: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            if 'conn' in locals():
                conn.close()

# Service de notification pour les courses
class NotificationService:
    @staticmethod
    def envoyer_notification_course(course_id):
        """Envoyer une notification à tous les chauffeurs du type de véhicule demandé"""
        try:
            course = Course.objects.get(id=course_id)
            type_vehicule_demande = course.type_vehicule_demande
            
            print(f"🚀 DÉBUT Notification course {course_id} - Type: {type_vehicule_demande}")
            
            # 1. Envoyer les notifications WebSocket
            try:
                channel_layer = get_channel_layer()
                if channel_layer is not None:
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
                    print(f"🔔 Notification WebSocket envoyée pour course {course_id}")
                else:
                    print("⚠ Channel layer non disponible")
            except Exception as e:
                print(f"⚠ Erreur WebSocket: {e}")
                import traceback
                traceback.print_exc()
            
            # 2. ENVOYER LES SMS AUX CHAUFFEURS
            print(f"📱 Début envoi SMS aux chauffeurs...")
            resultat_sms = SMSService.envoyer_sms_chauffeurs(course_id)
            print(f"📱 Résultat envoi SMS: {resultat_sms}")
            
            print(f"✅ FIN Notification course {course_id}")
            return True
                
        except Course.DoesNotExist:
            print(f"❌ Course {course_id} non trouvée")
            return False
        except Exception as e:
            print(f"❌ Erreur notification: {e}")
            import traceback
            traceback.print_exc()
            return False

    @staticmethod
    def notifier_confirmation_course(course_id, chauffeur_id):
        """Notifier que la course a été confirmée"""
        try:
            course = Course.objects.get(id=course_id)
            chauffeur = Chauffeur.objects.get(id=chauffeur_id)
            type_vehicule_demande = course.type_vehicule_demande
            
            print(f"🚀 DÉBUT Confirmation course {course_id} par chauffeur {chauffeur_id}")
            
            # 1. Notifications WebSocket
            try:
                channel_layer = get_channel_layer()
                if channel_layer is not None:
                    async_to_sync(channel_layer.group_send)(
                        f"chauffeurs_{type_vehicule_demande}",
                        {
                            "type": "course_confirmed",
                            "message": "Cette course a été confirmée par un autre chauffeur",
                            "course_id": course.id,
                            "chauffeur_name": str(chauffeur)
                        }
                    )
                    print(f"🔔 Notification WebSocket confirmation envoyée")
                else:
                    print("⚠ Channel layer non disponible pour confirmation")
            except Exception as e:
                print(f"⚠ Erreur WebSocket confirmation: {e}")
                import traceback
                traceback.print_exc()
            
            # 2. ENVOYER SMS DE CONFIRMATION AU CLIENT
            print(f"📱 Début envoi SMS confirmation au client...")
            resultat_sms_client = SMSService.envoyer_sms_confirmation_client(course_id)
            print(f"📱 Résultat SMS client: {resultat_sms_client}")
            
            print(f"✅ FIN Confirmation notifiée pour course {course_id}")
            return True
                
        except (Course.DoesNotExist, Chauffeur.DoesNotExist) as e:
            print(f"❌ Erreur confirmation: {e}")
            import traceback
            traceback.print_exc()
            return False
        except Exception as e:
            print(f"❌ Erreur générale confirmation: {e}")
            import traceback
            traceback.print_exc()
            return False

def send_welcome_sms_taxi(phone, username, role, password=None):
    """Envoi un SMS de bienvenue pour les utilisateurs taxi (clients et chauffeurs)"""
    try:
        if not phone:
            logger.warning("Aucun numéro de téléphone disponible pour l'envoi du SMS de bienvenue")
            return False

        print(f"📱 Envoi SMS bienvenue à {phone} pour {username} ({role})")

        # Validation et formatage international
        try:
            parsed = phonenumbers.parse(phone, "GN")
            if not phonenumbers.is_valid_number(parsed):
                logger.error(f"Numéro invalide: {phone}")
                return False
            phone_e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            logger.error(f"Erreur de parsing du numéro: {phone}")
            return False

        # Configuration requête
        conn = http.client.HTTPSConnection("api.nimbasms.com", timeout=10)
        headers = {
            "Authorization": settings.NIMBASMS_API_KEY.strip(),
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

        # Message de bienvenue personnalisé selon le rôle
        if role == 'client':
            message = (
                f"Bienvenue {username} sur notre plateforme de taxi Clappy CO!\n"
                "Votre compte client a été créé avec succès.\n"
                f"Votre mot de passe est : {password}\n"
                "Nous vous remercions pour votre confiance.\n"
                "📞 Service client: +224 627 57 95 31"
            )
        elif role == 'chauffeur':
            message = (
                f"Bienvenue {username} sur notre plateforme de taxi!\n"
                "Votre compte chauffeur a été créé avec succès.\n"
                f"Votre mot de passe est : {password}\n"
                "Nous vous remercions pour votre confiance.\n"
                "📞 Service client: +224 627 57 95 31"
            )
        else:
            message = (
                f"Bienvenue {username} sur notre plateforme de taxi!\n"
                "Votre compte a été créé avec succès.\n"
                f"Votre mot de passe est : {password}\n" if password else ""
                "Nous vous remercions pour votre confiance.\n"
                "📞 Service client: +224 627 57 95 31"
            )

        payload = {
            "to": [phone_e164],
            "sender_name": settings.NIMBASMS_SENDER_NAME,
            "message": message
        }

        # Envoi et vérification
        conn.request("POST", "/v1/messages", body=json.dumps(payload), headers=headers)
        response = conn.getresponse()
        response_body = response.read().decode()
        
        logger.info(f"Réponse NimbaSMS (taxi): {response.status} {response_body}")
        
        if response.status == 201:
            logger.info(f"SMS de bienvenue taxi envoyé avec succès! Utilisateur {username}")
            return True
            
        logger.error(f"Erreur SMS (taxi) {response.status}: {response_body}")
        return False

    except Exception as e:
        logger.error(f"Erreur SMS (taxi): {str(e)}", exc_info=True)
        return False
    finally:
        if 'conn' in locals():
            conn.close()

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

class IsAdminOrChauffeurOwner(permissions.BasePermission):
    """
    Permet aux administrateurs de faire toutes les actions.
    Permet aux chauffeurs de voir et modifier leur propre profil.
    """

    def has_permission(self, request, view):
        # Les administrateurs ont tous les droits
        if request.user and request.user.is_staff:
            return True

        # Les chauffeurs peuvent voir leur propre profil (action de détail) et le modifier
        # Mais ne peuvent pas lister tous les chauffeurs
        if view.action in ['retrieve', 'update', 'partial_update', 'statistiques', 'changer_statut']:
            return request.user and hasattr(request.user, 'chauffeur')
        else:
            return False

    def has_object_permission(self, request, view, obj):
        # Les administrateurs ont tous les droits
        if request.user and request.user.is_staff:
            return True

        # Un chauffeur ne peut accéder qu'à son propre profil
        if hasattr(request.user, 'chauffeur'):
            return obj.utilisateur == request.user
        return False

class LogoutRefreshView(APIView):
    """
    Blacklist the provided refresh token so it cannot be used again.
    Accepts { "refresh": "<refresh_token>" } in POST body.
    """
    permission_classes = (AllowAny,)
    
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
    permission_classes = [AllowAny]
    queryset = Client.objects.all().select_related('utilisateur')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return ClientCreateSerializer
        return ClientSerializer

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
                
                # ENVOI DU SMS DE BIENVENUE POUR LE CLIENT
                if client.telephone:
                    threading.Thread(
                        target=send_welcome_sms_taxi,
                        args=(client.telephone, client.utilisateur.username, 'client', request.data.get('password')),
                        daemon=True
                    ).start()
                    print(f"📱 SMS de bienvenue programmé pour le client {client.telephone}")
                else:
                    print("ℹ️ Pas de numéro de téléphone, aucun SMS envoyé")
                
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
    
    def get_permissions(self):
        """
        Permissions différenciées selon l'action
        """
        if self.action in ['create']:
            permission_classes = [AllowAny]
        elif self.action in ['list']:
            permission_classes = [AllowAny]
        else:
            permission_classes = [AllowAny]
        return [permission() for permission in permission_classes]

    def get_serializer_class(self):
        if self.action == 'create':
            return ChauffeurCreateSerializer
        return ChauffeurSerializer

    def create(self, request, *args, **kwargs):
        """
        Création d'un chauffeur + compte utilisateur lié avec gestion des doublons
        """
        print("🎯 Données reçues pour création chauffeur:", request.data)
        password = request.data.get('password')
        
        # VÉRIFICATION PRÉALABLE DES DOUBLONS
        username = request.data.get('username')
        telephone = request.data.get('telephone')
        email = request.data.get('email')
        
        errors = {}
        
        if username and User.objects.filter(username=username).exists():
            errors['username'] = ['Un utilisateur avec ce nom existe déjà']
        
        if telephone and Chauffeur.objects.filter(telephone=telephone).exists():
            errors['telephone'] = ['Un chauffeur avec ce numéro existe déjà']
        
        if email and User.objects.filter(email=email).exists():
            errors['email'] = ['Un utilisateur avec cet email existe déjà']
        
        if errors:
            print("❌ Erreurs de doublons détectées:", errors)
            return Response(
                {"detail": "Erreurs de validation", "errors": errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = self.get_serializer(data=request.data)
        
        if serializer.is_valid():
            print("✅ Données valides")
            try:
                chauffeur = serializer.save()
                print(f"✅ Chauffeur créé: {chauffeur.id}, Utilisateur: {chauffeur.utilisateur.id}")
                print(f"🔑 Mot de passe récupéré: {password}")
                
                # ENVOI DU SMS DE BIENVENUE POUR LE CHAUFFEUR AVEC LE MOT DE PASSE
                if chauffeur.telephone:
                    threading.Thread(
                        target=send_welcome_sms_taxi,
                        args=(chauffeur.telephone, chauffeur.utilisateur.username, 'chauffeur', password),
                        daemon=True
                    ).start()
                    print(f"📱 SMS de bienvenue programmé pour le chauffeur {chauffeur.telephone} avec mot de passe: {password}")
                else:
                    print("ℹ️ Pas de numéro de téléphone, aucun SMS envoyé")
                
                return Response(
                    ChauffeurSerializer(chauffeur, context={'request': request}).data,
                    status=status.HTTP_201_CREATED
                )
                
            except Exception as e:
                print(f"❌ Erreur lors de la création du chauffeur: {e}")
                return Response(
                    {"detail": f"Erreur lors de la création: {str(e)}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            print("❌ Erreurs de validation DÉTAILLÉES:", serializer.errors)
            return Response(
                {
                    "detail": "Erreurs de validation du sérialiseur",
                    "errors": serializer.errors
                }, 
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'])
    def serializer_info(self, request):
        """Endpoint temporaire pour voir la structure du sérialiseur"""
        serializer = self.get_serializer()
        return Response({
            'fields': list(serializer.fields.keys()),
            'required_fields': [name for name, field in serializer.fields.items() if field.required]
        })

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

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.select_related('client', 'chauffeur', 'paiement', 'evaluation').all()
    serializer_class = CourseSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        try:
            course = serializer.save(statut='demandee', date_demande=timezone.now())
            print(f"✅ Course {course.id} créée avec succès")
            print(f"📋 Détails course: Type={course.type_vehicule_demande}, Départ={course.adresse_depart}")

            try:
                # 🔥 CETTE MÉTHODE ENVOIE MAINTENANT LES SMS + WEBSOCKET
                print(f"🚀 Lancement notifications pour course {course.id}")
                NotificationService.envoyer_notification_course(course.id)
                print(f"✅ Notifications lancées pour course {course.id}")
            except Exception as e:
                print(f"⚠ Notification échouée: {e}")
                import traceback
                traceback.print_exc()
        except Exception as e:
            print(f"❌ Erreur création course: {e}")
            import traceback
            traceback.print_exc()
            raise

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        # 🚖 Si c'est un chauffeur connecté
        if hasattr(user, 'chauffeur'):
            chauffeur = user.chauffeur

            try:
                vehicule = Vehicule.objects.get(chauffeur=chauffeur)
                type_vehicule = vehicule.type_vehicule

                # ✅ Le chauffeur voit uniquement :
                # - les courses de son type de véhicule
                # - qui sont demandées ou qu'il a acceptées
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
        print(f"🚖 Chauffeur {chauffeur_id} tente d'accepter la course {course.id}")
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

            # 🔥 CETTE MÉTHODE ENVOIE MAINTENANT LE SMS DE CONFIRMATION AU CLIENT
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
        maintenant = timezone.now()
        mois_courant = maintenant.month
        annee_courante = maintenant.year

        print(f"🔍 DEBUG RevenuMensuel - Mois: {mois_courant}, Année: {annee_courante}")
        
        courses = Course.objects.filter(
            statut='terminee',
            date_fin__year=annee_courante,
            date_fin__month=mois_courant
        )

        revenu_total = courses.aggregate(total=Sum('tarif_final'))['total'] or 0
        nombre_courses = courses.count()

        data = {
            "annee": annee_courante,
            "mois": maintenant.strftime("%B"),
            "revenu_total": float(revenu_total),
            "nombre_courses": nombre_courses,
            "debug": {
                "courses_count": courses.count(),
                "current_month": mois_courant,
                "current_year": annee_courante
            }
        }

        print(f"🔍 DEBUG RevenuMensuel - Données renvoyées: {data}")
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

        # Filtrer les courses terminées ce mois
        courses = Course.objects.filter(
            statut='terminee',
            date_fin__year=annee_courante,
            date_fin__month=mois_courant,
            chauffeur__isnull=False
        )

        # Grouper par chauffeur et calculer le revenu total
        chauffeurs_revenus = (
            courses.values('chauffeur_id', 'chauffeur__utilisateur__username', 'chauffeur__utilisateur__first_name', 'chauffeur__utilisateur__last_name')
            .annotate(revenu_total=Sum('tarif_final'))
            .order_by('-revenu_total')
        )

        if chauffeurs_revenus.exists():
            meilleur = chauffeurs_revenus.first()
            
            # Calculer la note moyenne du chauffeur pour le mois en cours
            evaluations = Evaluation.objects.filter(
                course__chauffeur_id=meilleur['chauffeur_id'],
                course__date_fin__year=annee_courante,
                course__date_fin__month=mois_courant
            ).aggregate(note_moyenne=Avg('note_chauffeur'))

            note_moyenne = evaluations['note_moyenne'] or 0

            # Construire le nom complet
            nom_complet = f"{meilleur['chauffeur__utilisateur__first_name']} {meilleur['chauffeur__utilisateur__last_name']}".strip()
            if not nom_complet:
                nom_complet = meilleur['chauffeur__utilisateur__username']

            data = {
                "annee": annee_courante,
                "mois": maintenant.strftime("%B"),
                "chauffeur_id": meilleur['chauffeur_id'],
                "chauffeur_nom": meilleur['chauffeur__utilisateur__username'],
                "nom_complet": nom_complet,
                "revenu_total": float(meilleur['revenu_total']),
                "note_moyenne": round(note_moyenne, 1)
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

class NombreClientsTotalView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        """
        Version simplifiée pour le dashboard - retourne juste le nombre total
        """
        try:
            nombre_clients = Client.objects.count()
            
            return Response({
                "nombre_clients": nombre_clients
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                "nombre_clients": 0,
                "erreur": str(e)
            }, status=status.HTTP_200_OK)

#Verifier si le numero que le client a entrer pour la creation de son compte existe deja dans la base
@method_decorator(csrf_exempt, name='dispatch')
class CheckPhoneView(APIView):
    permission_classes = [AllowAny]
    
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

# Vue pour tester les SMS
class TestSMSNotificationView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        course_id = request.data.get('course_id')
        if not course_id:
            return Response(
                {"erreur": "L'ID de la course est requis"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Tester l'envoi de SMS aux chauffeurs
        success_sms_chauffeurs = SMSService.envoyer_sms_chauffeurs(course_id)
        
        # Tester l'envoi de SMS de confirmation au client
        success_sms_client = SMSService.envoyer_sms_confirmation_client(course_id)
        
        return Response({
            "sms_chauffeurs_envoye": success_sms_chauffeurs,
            "sms_client_envoye": success_sms_client,
            "message": "Tests SMS effectués"
        })

# Vue pour tester la recherche des chauffeurs par type de véhicule
class TestChauffeursParTypeView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        type_vehicule = request.query_params.get('type_vehicule')
        
        if not type_vehicule:
            return Response(
                {"erreur": "Le paramètre type_vehicule est requis"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Récupérer les chauffeurs avec le type de véhicule demandé
        chauffeurs = Chauffeur.objects.filter(
            vehicule__type_vehicule=type_vehicule,
            statut='disponible'
        ).select_related('vehicule', 'utilisateur')

        data = []
        for chauffeur in chauffeurs:
            data.append({
                'id': chauffeur.id,
                'nom': str(chauffeur),
                'telephone': chauffeur.telephone,
                'statut': chauffeur.statut,
                'vehicule': {
                    'type_vehicule': chauffeur.vehicule.type_vehicule,
                    'marque': chauffeur.vehicule.marque,
                    'modele': chauffeur.vehicule.modele,
                    'immatriculation': chauffeur.vehicule.immatriculation
                } if chauffeur.vehicule else None
            })

        return Response({
            "type_vehicule": type_vehicule,
            "nombre_chauffeurs": len(data),
            "chauffeurs": data
        })

# Vue pour tester l'envoi SMS directement
class TestSMSSimpleView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        telephone = request.data.get('telephone')
        message = request.data.get('message', "Test SMS depuis l'API")
        
        if not telephone:
            return Response(
                {"erreur": "Le numéro de téléphone est requis"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            success = SMSService._envoyer_sms(telephone, message)
            
            if success:
                return Response({
                    "message": "SMS envoyé avec succès",
                    "telephone": telephone
                })
            else:
                return Response({
                    "erreur": "Échec de l'envoi du SMS",
                    "telephone": telephone
                }, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            return Response({
                "erreur": f"Exception lors de l'envoi: {str(e)}"
            }, status=status.HTTP_400_BAD_REQUEST)