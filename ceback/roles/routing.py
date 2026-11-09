from django.urls import re_path

from .consumers import NotificationConsumer, SlotConsumer

websocket_urlpatterns = [
    re_path(r'^ws/notifications/$', NotificationConsumer.as_asgi()),
    re_path(r'^ws/slots/(?P<slot_id>\d+)/$', SlotConsumer.as_asgi()),
]