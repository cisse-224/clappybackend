# models.py
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth.models import AbstractUser
from django.utils import timezone

# --------- CustomUser ---------
class CustomUser(AbstractUser):
    telephone = models.CharField(max_length=15, unique=True, null=True, blank=True)
    is_client = models.BooleanField(default=False)
    is_chauffeur = models.BooleanField(default=False)

# --------- Client ---------
class Client(models.Model):
    """Modèle pour les clients qui utilisent l'application"""
    utilisateur = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Utilisateur")
    telephone = models.CharField(max_length=15, verbose_name="Téléphone")
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    date_modification = models.DateTimeField(auto_now=True, verbose_name="Date de modification")
    
    class Meta:
        verbose_name = "Client"
        verbose_name_plural = "Clients"
    
    def _str_(self):
        return f"{self.utilisateur.get_full_name() or self.utilisateur.username}"

# --------- Chauffeur ---------
class Chauffeur(models.Model):
    """Modèle pour les chauffeurs de taxi"""
    
    STATUT_CHOIX = [
        ('disponible', 'Disponible'),
        ('en_course', 'En course'),
        ('hors_ligne', 'Hors ligne'),
        ('en_pause', 'En pause'),
    ]
    
    utilisateur = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, verbose_name="Utilisateur")
    telephone = models.CharField(max_length=15, verbose_name="Téléphone")
    numero_permis = models.CharField(max_length=20, unique=True, verbose_name="Numéro de permis")
    statut = models.CharField(max_length=15, choices=STATUT_CHOIX, default='hors_ligne', verbose_name="Statut")
    est_approuve = models.BooleanField(default=False, verbose_name="Est approuvé")
    note_moyenne = models.DecimalField(max_digits=3, decimal_places=2, default=5.0, verbose_name="Note moyenne")
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    date_modification = models.DateTimeField(auto_now=True, verbose_name="Date de modification")

    class Meta:
        ordering = ['id']
        verbose_name = "Chauffeur"
        verbose_name_plural = "Chauffeurs"
    
    def _str_(self):
        return f"{self.utilisateur.get_full_name() or self.utilisateur.username} - {self.numero_permis}"

# --------- Vehicule ---------
class Vehicule(models.Model):
    TYPE_VEHICULE_CHOIX = [
        ('climatiser', 'Climatiser'),
        ('economique', 'Economique'),
        ('vip', 'VIP'),
        ('moto', 'Moto'),
    ]
    
    chauffeur = models.OneToOneField(Chauffeur, on_delete=models.CASCADE, verbose_name="Chauffeur")
    marque = models.CharField(max_length=50, verbose_name="Marque")
    modele = models.CharField(max_length=50, verbose_name="Modèle")
    annee = models.IntegerField(verbose_name="Année")
    immatriculation = models.CharField(max_length=15, unique=True, verbose_name="Plaque d'immatriculation")
    couleur = models.CharField(max_length=30, verbose_name="Couleur")
    type_vehicule = models.CharField(max_length=15, choices=TYPE_VEHICULE_CHOIX, default='berline', verbose_name="Type de véhicule")
    nombre_places = models.IntegerField(default=4, verbose_name="Nombre de places")
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    
    class Meta:
        verbose_name = "Véhicule"
        verbose_name_plural = "Véhicules"
    
    def _str_(self):
        return f"{self.marque} {self.modele} - {self.immatriculation}"

# --------- Course ---------
class Course(models.Model):
    STATUT_CHOIX = [
        ('demandee', 'Demandée'),
        ('acceptee', 'Acceptée'),
        ('en_cours', 'En cours'),
        ('terminee', 'Terminée'),
        ('annulee', 'Annulée'),
    ]
    
    METHODE_PAIEMENT_CHOIX = [
        ('especes', 'Espèces'),
        ('mobile_money', 'Mobile Money'),
        ('carte_bancaire', 'Carte Bancaire'),
    ]
    
    TYPE_COURSE_CHOIX = [
        ('immediate', 'Course immédiate'),
        ('reservation', 'Réservation'),
    ]
    
    type_vehicule_demande = models.CharField(
        max_length=15, 
        choices=Vehicule.TYPE_VEHICULE_CHOIX, 
        verbose_name="Type de véhicule demandé"
    )
    client = models.ForeignKey(Client, on_delete=models.CASCADE, verbose_name="Client")
    chauffeur = models.ForeignKey(Chauffeur, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Chauffeur")
    adresse_depart = models.TextField(verbose_name="Adresse de départ")
    adresse_destination = models.TextField(verbose_name="Adresse de destination")
    latitude_depart = models.DecimalField(max_digits=25, decimal_places=20, null=True, blank=True, verbose_name="Latitude départ")
    longitude_depart = models.DecimalField(max_digits=25, decimal_places=20, null=True, blank=True, verbose_name="Longitude départ")
    latitude_destination = models.DecimalField(max_digits=25, decimal_places=20, null=True, blank=True, verbose_name="Latitude destination")
    longitude_destination = models.DecimalField(max_digits=25, decimal_places=20, null=True, blank=True, verbose_name="Longitude destination")
    type_course = models.CharField(max_length=15, choices=TYPE_COURSE_CHOIX, default='immediate', verbose_name="Type de course")
    date_demande = models.DateTimeField(auto_now_add=True, verbose_name="Date de demande")
    date_acceptation = models.DateTimeField(null=True, blank=True, verbose_name="Date d'acceptation")
    date_debut = models.DateTimeField(null=True, blank=True, verbose_name="Date de début")
    date_fin = models.DateTimeField(null=True, blank=True, verbose_name="Date de fin")
    date_reservation = models.DateTimeField(default=timezone.now)
    tarif_estime = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Tarif estimé (GNF)")
    tarif_final = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name="Tarif final (GNF)")
    distance_estimee = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, verbose_name="Distance estimée (km)")
    duree_estimee = models.IntegerField(null=True, blank=True, verbose_name="Durée estimée (minutes)")
    statut = models.CharField(max_length=15, choices=STATUT_CHOIX, default='demandee', verbose_name="Statut")
    methode_paiement = models.CharField(max_length=15, choices=METHODE_PAIEMENT_CHOIX, verbose_name="Méthode de paiement")
    notes_client = models.TextField(blank=True, verbose_name="Notes du client")
    
    class Meta:
        verbose_name = "Course"
        verbose_name_plural = "Courses"
        ordering = ['-date_demande']
    
    def _str_(self):
        return f"Course #{self.id} - {self.client}"

# --------- Paiement ---------
class Paiement(models.Model):
    STATUT_PAIEMENT_CHOIX = [
        ('en_attente', 'En attente'),
        ('paye', 'Payé'),
        ('echoue', 'Échoué'),
        ('rembourse', 'Remboursé'),
    ]
    
    course = models.OneToOneField(Course, on_delete=models.CASCADE, verbose_name="Course")
    montant = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Montant (GNF)")
    identifiant_transaction = models.CharField(max_length=100, blank=True, verbose_name="Identifiant de transaction")
    statut_paiement = models.CharField(max_length=15, choices=STATUT_PAIEMENT_CHOIX, default='en_attente', verbose_name="Statut du paiement")
    date_paiement = models.DateTimeField(auto_now_add=True, verbose_name="Date de paiement")
    date_confirmation = models.DateTimeField(null=True, blank=True, verbose_name="Date de confirmation")
    operateur_mobile_money = models.CharField(max_length=20, blank=True, verbose_name="Opérateur Mobile Money")
    numero_mobile_money = models.CharField(max_length=15, blank=True, verbose_name="Numéro Mobile Money")
    
    class Meta:
        verbose_name = "Paiement"
        verbose_name_plural = "Paiements"
    
    def _str_(self):
        return f"Paiement #{self.id} - {self.montant} GNF - {self.course}"

# --------- Evaluation ---------
class Evaluation(models.Model):
    course = models.OneToOneField(Course, on_delete=models.CASCADE, verbose_name="Course")
    chauffeur = models.ForeignKey(Chauffeur, on_delete=models.CASCADE, verbose_name="Chauffeur")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, verbose_name="Client")
    note_chauffeur = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name="Note du chauffeur (1-5)")
    note_vehicule = models.IntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)], verbose_name="Note du véhicule (1-5)")
    commentaire = models.TextField(blank=True, verbose_name="Commentaire")
    date_evaluation = models.DateTimeField(auto_now_add=True, verbose_name="Date d'évaluation")
    
    class Meta:
        verbose_name = "Évaluation"
        verbose_name_plural = "Évaluations"
    
    def _str_(self):
        return f"Évaluation #{self.id} - {self.note_chauffeur}/5"

# --------- HistoriquePosition ---------
class HistoriquePosition(models.Model):
    chauffeur = models.ForeignKey(Chauffeur, on_delete=models.CASCADE, verbose_name="Chauffeur")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, verbose_name="Latitude")
    longitude = models.DecimalField(max_digits=9, decimal_places=6, verbose_name="Longitude")
    date_position = models.DateTimeField(auto_now_add=True, verbose_name="Date de position")
    
    class Meta:
        verbose_name = "Historique de position"
        verbose_name_plural = "Historiques de position"
        ordering = ['-date_position']
    
    def _str_(self):
        return f"Position {self.chauffeur} - {self.date_position}"

# --------- Tarif ---------
class Tarif(models.Model):
    type_vehicule = models.CharField(max_length=15, choices=Vehicule.TYPE_VEHICULE_CHOIX, verbose_name="Type de véhicule")
    prix_base = models.DecimalField(max_digits=8, decimal_places=2, verbose_name="Prix de base (GNF)")
    prix_par_km = models.DecimalField(max_digits=8, decimal_places=2, verbose_name="Prix par km (GNF)")
    est_actif = models.BooleanField(default=True, verbose_name="Est actif")
    date_creation = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    
    class Meta:
        verbose_name = "Tarif"
        verbose_name_plural = "Tarifs"
    
    def _str_(self):
        return f"Tarif {self.type_vehicule} - {self.prix_par_km} GNF/km"