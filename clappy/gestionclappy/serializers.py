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
            print(f"🔐 Mot de passe généré: {password}")
        
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

# ⬇️⬇️⬇️ AJOUTER CE ClientSerializer MANQUANT ⬇️⬇️⬇️
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
    client_nom_complet = serializers.CharField(source='client.utilisateur.get_full_name', read_only=True)
    chauffeur_nom_complet = serializers.CharField(source='chauffeur.utilisateur.get_full_name', read_only=True)
    duree_totale = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            'id',
            'client_nom_complet',
            'chauffeur_nom_complet',
            'adresse_depart',
            'adresse_destination',
            'type_course',
            'statut',
            'methode_paiement',
            'tarif_estime',
            'tarif_final',
            'duree_totale',
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