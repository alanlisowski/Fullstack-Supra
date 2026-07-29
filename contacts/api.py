from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from contacts.models import Contact
from contacts.serializers import ContactSerializer
from contacts.services import CityNotFound, WeatherUnavailable, get_city_weather

ORDERING_ALLOWED = {"last_name", "-last_name", "created_at", "-created_at"}


class ContactViewSet(ModelViewSet):
    serializer_class = ContactSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Filtering by owner is what makes cross-user access 404 instead of
        # 403: a foreign PK simply doesn't exist in this queryset.
        qs = Contact.objects.filter(owner=self.request.user).select_related("status")

        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(first_name__icontains=search) | Q(last_name__icontains=search)
                | Q(email__icontains=search) | Q(city__icontains=search)
            )

        ordering = self.request.query_params.get("ordering")
        if ordering in ORDERING_ALLOWED:
            qs = qs.order_by(ordering)

        return qs

    # No perform_create override: the serializer's owner field uses
    # CurrentUserDefault, so ownership is set from the session there.


@api_view(["GET"])
# Without this the endpoint is public, which turns the app into an open proxy
# to Nominatim and Open-Meteo under our own User-Agent.
@permission_classes([IsAuthenticated])
def city_weather(request):
    city = request.query_params.get("city")
    if not city:
        return Response(
            {"error": "missing_city", "detail": "Provide a ?city= parameter."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        return Response(get_city_weather(city))
    except CityNotFound:
        # 404: the city genuinely doesn't exist. Only the user can fix this.
        return Response(
            {"error": "city_not_found", "detail": f"No place matching '{city}'."},
            status=status.HTTP_404_NOT_FOUND,
        )
    except WeatherUnavailable:
        # 503: our upstreams are down. Nothing wrong with the contact's data,
        # and the client should feel free to retry later.
        return Response(
            {"error": "weather_unavailable", "detail": "Weather service is temporarily unavailable."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
