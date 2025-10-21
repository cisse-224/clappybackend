# routing.py
from django.urls import re_path

from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/chauffeur/$', consumers.ChauffeurConsumer.as_asgi()),
]