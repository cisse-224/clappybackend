from rest_framework import serializers
from .models import Client, Chauffeur, Vehicule, Course, Paiement, Evaluation, HistoriquePosition, Tarif
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Infos de base
        token['username'] = user.username
        token['email'] = user.email

        # Vérifier si l'utilisateur est Client
        if hasattr(user, "client"):
            token['role'] = "client"
            token['telephone'] = user.client.telephone
            token['id_client'] = user.client.id

        # Vérifier si l'utilisateur est Chauffeur
        elif hasattr(user, "chauffeur"):
            token['role'] = "chauffeur"
            token['telephone'] = user.chauffeur.telephone
            token['id_chauffeur'] = user.chauffeur.id

        else:
            token['role'] = "admin" if user.is_staff else "user"

        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        # Ajouter infos aussi dans la réponse (utile côté front)
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

class ClientSerializer(serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='client-detail')
    
    class Meta:
        model = Client
        fields = ['url', 'id', 'utilisateur', 'telephone', 'date_creation', 'date_modification']
        read_only_fields = ['date_creation', 'date_modification']

class ChauffeurSerializer(serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='chauffeur-detail')
    nom_complet = serializers.SerializerMethodField()
    
    class Meta:
        model = Chauffeur
        fields = [
            'url', 'id', 'utilisateur', 'telephone', 'numero_permis', 'statut', 
            'est_approuve', 'note_moyenne', 'nom_complet', 'date_creation', 'date_modification'
        ]
        read_only_fields = ['date_creation', 'date_modification', 'note_moyenne']
    
    def get_nom_complet(self, obj):
        return f"{obj.utilisateur.first_name} {obj.utilisateur.last_name}"

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

class CourseSerializer(serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='course-detail')
    client_nom = serializers.CharField(source='client.utilisateur.get_full_name', read_only=True)
    chauffeur_nom = serializers.CharField(source='chauffeur.utilisateur.get_full_name', read_only=True)
    duree_totale = serializers.SerializerMethodField()
    
    class Meta:
        model = Course
        fields = [
            'url', 'id', 'client', 'client_nom', 'chauffeur', 'chauffeur_nom',
            'adresse_depart', 'adresse_destination', 'latitude_depart', 'longitude_depart',
            'latitude_destination', 'longitude_destination', 'type_course', 'date_demande',
            'date_acceptation', 'date_debut', 'date_fin', 'date_reservation', 'tarif_estime',
            'tarif_final', 'distance_estimee', 'duree_estimee', 'statut', 'methode_paiement',
            'notes_client', 'duree_totale'
        ]
        read_only_fields = ['date_demande']
    
    def get_duree_totale(self, obj):
        if obj.date_debut and obj.date_fin:
            return (obj.date_fin - obj.date_debut).total_seconds() / 60
        return None

class PaiementSerializer(serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='paiement-detail')
    course_info = serializers.CharField(source='course.id', read_only=True)
    
    class Meta:
        model = Paiement
        fields = [
            'url', 'id', 'course', 'course_info', 'montant', 'identifiant_transaction',
            'statut_paiement', 'date_paiement', 'date_confirmation', 'operateur_mobile_money',
            'numero_mobile_money'
        ]
        read_only_fields = ['date_paiement']

class EvaluationSerializer(serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='evaluation-detail')
    client_nom = serializers.CharField(source='client.utilisateur.get_full_name', read_only=True)
    chauffeur_nom = serializers.CharField(source='chauffeur.utilisateur.get_full_name', read_only=True)
    
    class Meta:
        model = Evaluation
        fields = [
            'url', 'id', 'course', 'chauffeur', 'chauffeur_nom', 'client', 'client_nom',
            'note_chauffeur', 'note_vehicule', 'commentaire', 'date_evaluation'
        ]
        read_only_fields = ['date_evaluation']

class HistoriquePositionSerializer(serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='historiqueposition-detail')
    chauffeur_nom = serializers.CharField(source='chauffeur.utilisateur.get_full_name', read_only=True)
    
    class Meta:
        model = HistoriquePosition
        fields = ['url', 'id', 'chauffeur', 'chauffeur_nom', 'latitude', 'longitude', 'date_position']
        read_only_fields = ['date_position']

class TarifSerializer(serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='tarif-detail')
    
    class Meta:
        model = Tarif
        fields = [
            'url', 'id', 'type_vehicule', 'prix_base', 'prix_par_km',
            'frais_service', 'est_actif', 'date_creation'
        ]
        read_only_fields = ['date_creation']