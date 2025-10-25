import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import gestionclappy.routing  # Si vous avez du routing WebSocket

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'clappy.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            gestionclappy.routing.websocket_urlpatterns  # Si vous avez des routes WebSocket
        )
    ),
})