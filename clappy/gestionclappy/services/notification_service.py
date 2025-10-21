# services/notification_service.py
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone
from models import Course, Vehicule, Chauffeur

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
                    "tarif_estime": course.tarif_estime,
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