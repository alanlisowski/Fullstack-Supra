from django.urls import path
from rest_framework.routers import DefaultRouter

from contacts.api import ContactViewSet, city_weather

router = DefaultRouter()
router.register("contacts", ContactViewSet, basename="contact")

urlpatterns = [
    path("weather/", city_weather, name="city-weather"),
] + router.urls
