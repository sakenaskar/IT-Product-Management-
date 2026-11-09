from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    BookingViewSet, ClientViewSet, DoctorViewSet, ManagerViewSet,
    NotificationViewSet, SlotViewSet,
)

router = DefaultRouter()
router.register('clients', ClientViewSet, basename='client')
router.register('doctors', DoctorViewSet, basename='doctor')
router.register('managers', ManagerViewSet, basename='manager')
router.register('slots', SlotViewSet, basename='slot')
router.register('bookings', BookingViewSet, basename='booking')
router.register('notifications', NotificationViewSet, basename='notification')

urlpatterns = [
    path('', include(router.urls)),
]