from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import json
from .models import Chauffeur

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.type_vehicule = self.scope['url_route']['kwargs']['type_vehicule']
        self.room_group_name = f'chauffeurs_{self.type_vehicule}'
        
        # Vérifier si l'utilisateur est un chauffeur
        if await self.est_chauffeur():
            # Rejoindre le groupe
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
            
            # Marquer le chauffeur comme en ligne
            await self.mettre_en_ligne(True)
        else:
            await self.close()

    async def disconnect(self, close_code):
        # Quitter le groupe
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )
        # Marquer le chauffeur comme hors ligne
        await self.mettre_en_ligne(False)

    async def receive(self, text_data):
        # Les chauffeurs peuvent envoyer des messages si besoin
        pass

    # Recevoir une notification du groupe
    async def envoyer_notification(self, event):
        message = event['message']
        course_data = event['course_data']
        
        # Envoyer au WebSocket
        await self.send(text_data=json.dumps({
            'type': 'nouvelle_course',
            'message': message,
            'course': course_data
        }))

    @database_sync_to_async
    def est_chauffeur(self):
        return Chauffeur.objects.filter(user=self.scope['user']).exists()

    @database_sync_to_async
    def mettre_en_ligne(self, status):
        try:
            chauffeur = Chauffeur.objects.get(user=self.scope['user'])
            chauffeur.en_ligne = status
            chauffeur.save()
            return True
        except Chauffeur.DoesNotExist:
            return False