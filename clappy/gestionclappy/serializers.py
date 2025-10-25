from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Client, Chauffeur, Vehicule, Course, Paiement, Evaluation, HistoriquePosition, Tarif
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

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
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']

# ================= CLIENT =================
class ClientSerializer(serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='client-detail')
    class Meta:
        model = Client
        fields = ['url', 'id', 'utilisateur', 'telephone', 'date_creation', 'date_modification']
        read_only_fields = ['date_creation', 'date_modification']


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

        # ✅ Création du CustomUser (et non de User par défaut)
        user = User.objects.create_user(username=username, password=password, email=email)

        # ✅ Création du chauffeur associé
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
    url = serializers.HyperlinkedIdentityField(view_name='course-detail')
    client_nom = serializers.CharField(source='client.utilisateur.get_full_name', read_only=True)
    chauffeur_nom = serializers.CharField(source='chauffeur.utilisateur.get_full_name', read_only=True)
    duree_totale = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            'url', 'id', 'client', 'client_nom','type_vehicule_demande',  'chauffeur', 'chauffeur_nom',
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


# ================= AUTRES =================
class PaiementSerializer(serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='paiement-detail')
    class Meta:
        model = Paiement
        fields = '__all__'


class EvaluationSerializer(serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='evaluation-detail')
    class Meta:
        model = Evaluation
        fields = '__all__'


class HistoriquePositionSerializer(serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='historiqueposition-detail')
    class Meta:
        model = HistoriquePosition
        fields = '__all__'


class TarifSerializer(serializers.ModelSerializer):
    url = serializers.HyperlinkedIdentityField(view_name='tarif-detail')
    class Meta:
        model = Tarif
        fields = '__all__'

# ================= CHANGEMENT DE MOT DE PASSE =================
from django.contrib.auth.password_validation import validate_password

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

