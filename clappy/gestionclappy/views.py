from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Count, Avg, Sum
from django.utils import timezone
from datetime import timedelta
from .models import Client, Chauffeur, Vehicule, Course, Paiement, Evaluation, HistoriquePosition, Tarif
from .serializers import *
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.contrib.auth import authenticate
from rest_framework import status

@api_view(['POST'])
def login_view(request):
    username = request.data.get('username')
    password = request.data.get('password')
    user = authenticate(username=username, password=password)
    if user:
        # Générer un token (SimpleJWT ou autre)
        return Response({'token': 'votre_token'})
    return Response({'detail': 'Identifiants invalides'}, status=status.HTTP_401_UNAUTHORIZED)

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

class ChauffeurViewSet(viewsets.ModelViewSet):
    queryset = Chauffeur.objects.all().select_related('utilisateur')
    serializer_class = ChauffeurSerializer
    permission_classes = [permissions.IsAuthenticated]
    
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
        
        # Calcul des statistiques
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
        return Response(
            {'erreur': 'Statut invalide'}, 
            status=status.HTTP_400_BAD_REQUEST
        )

class VehiculeViewSet(viewsets.ModelViewSet):
    queryset = Vehicule.objects.all().select_related('chauffeur__utilisateur')
    serializer_class = VehiculeSerializer
    permission_classes = [permissions.IsAuthenticated]

class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.all().select_related('client__utilisateur', 'chauffeur__utilisateur')
    serializer_class = CourseSerializer
    permission_classes = [permissions.IsAuthenticated]
    
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
        """Accepter une course"""
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
            
            return Response({'statut': 'Course acceptée'})
            
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
            statut_paiement='en_attente',
            methode_paiement=course.methode_paiement
        )
        
        return Response({'statut': 'Course terminée'})
    
    @action(detail=False, methods=['get'])
    def en_cours(self, request):
        """Liste des courses en cours"""
        courses = Course.objects.filter(statut='en_cours')
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