# services.py
import googlemaps
import json
from django.conf import settings
from decimal import Decimal

def geocode_address(address):
    """
    Convertit une adresse en coordonnées géographiques
    """
    try:
        gmaps = googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY)
        result = gmaps.geocode(str(address))
        
        if result:
            latitude = result[0]['geometry']['location']['lat']
            longitude = result[0]['geometry']['location']['lng']
            return Decimal(str(latitude)), Decimal(str(longitude))
        return None, None
    except Exception as e:
        print(f"Erreur de géocodage: {e}")
        return None, None

def calculate_route_distance_duration(origin_lat, origin_lng, dest_lat, dest_lng):
    """
    Calcule la distance et la durée entre deux points
    Retourne (distance_km, durée_minutes)
    """
    try:
        gmaps = googlemaps.Client(key=settings.GOOGLE_MAPS_API_KEY)
        result = gmaps.distance_matrix(
            origins=(origin_lat, origin_lng),
            destinations=(dest_lat, dest_lng),
            mode="driving",
            units="metric"
        )
        
        if result['rows'][0]['elements'][0]['status'] == 'OK':
            element = result['rows'][0]['elements'][0]
            distance_km = element['distance']['value'] / 1000  # Convertir en km
            duration_min = element['duration']['value'] / 60   # Convertir en minutes
            return Decimal(str(distance_km)), Decimal(str(duration_min))
        return None, None
    except Exception as e:
        print(f"Erreur calcul itinéraire: {e}")
        return None, None

def estimate_fare(distance_km, duration_min, vehicle_type='berline'):
    """
    Estime le tarif basé sur la distance, durée et type de véhicule
    """
    try:
        # Récupérer les tarifs depuis la base de données
        from .models import Tarif
        tarif = Tarif.objects.filter(type_vehicule=vehicle_type, est_actif=True).first()
        
        if tarif:
            fare = (tarif.prix_base + 
                   (distance_km * tarif.prix_par_km) + 
                   (duration_min * tarif.prix_par_minute))
            return Decimal(str(fare))
        
        # Tarif par défaut si aucun tarif trouvé
        return Decimal(str(5000 + (distance_km * 1500) + (duration_min * 200)))
    except Exception as e:
        print(f"Erreur estimation tarif: {e}")
        return Decimal('10000')  # Tarif minimum