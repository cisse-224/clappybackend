from django.contrib import admin


from .models import *


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['utilisateur', 'telephone', 'date_creation']
    search_fields = ['utilisateur__username', 'utilisateur__first_name', 'utilisateur__last_name', 'telephone']
    list_filter = ['date_creation']

@admin.register(Chauffeur)
class ChauffeurAdmin(admin.ModelAdmin):
    list_display = ['utilisateur', 'numero_permis', 'statut', 'est_approuve', 'note_moyenne']
    list_filter = ['statut', 'est_approuve', 'date_creation']
    search_fields = ['utilisateur__username', 'numero_permis', 'telephone']
    actions = ['approuver_chauffeurs']

    def approuver_chauffeurs(self, request, queryset):
        queryset.update(est_approuve=True)
    approuver_chauffeurs.short_description = "Approuver les chauffeurs sélectionnés"

@admin.register(Vehicule)
class VehiculeAdmin(admin.ModelAdmin):
    list_display = ['marque', 'modele', 'immatriculation', 'chauffeur', 'type_vehicule']
    list_filter = ['type_vehicule', 'annee']
    search_fields = ['marque', 'modele', 'immatriculation']

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['id', 'client', 'chauffeur', 'statut', 'tarif_estime', 'date_demande']
    list_filter = ['statut', 'type_course', 'methode_paiement', 'date_demande']
    search_fields = ['client__utilisateur__username', 'chauffeur__utilisateur__username']
    readonly_fields = ['date_demande']

@admin.register(Paiement)
class PaiementAdmin(admin.ModelAdmin):
    list_display = ['id', 'course', 'montant', 'statut_paiement', 'date_paiement']
    list_filter = ['statut_paiement', 'date_paiement']
    search_fields = ['identifiant_transaction', 'course__id']

@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = ['course', 'chauffeur', 'note_chauffeur', 'note_vehicule', 'date_evaluation']
    list_filter = ['note_chauffeur', 'note_vehicule', 'date_evaluation']

@admin.register(Tarif)
class TarifAdmin(admin.ModelAdmin):
    list_display = ['type_vehicule', 'prix_base', 'prix_par_km', 'est_actif']
    list_filter = ['type_vehicule', 'est_actif']

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'telephone', 'is_staff', 'is_active']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'telephone']
    list_filter = ['is_staff', 'is_active', 'is_client', 'is_chauffeur']