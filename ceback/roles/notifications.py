import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from .models import Notification

logger = logging.getLogger(__name__)


def user_group(user_id):
  return f'user_{user_id}'


def notify_user(user, kind, text, booking=None, slot=None):
  """Создаёт уведомление и после коммита пушит его по websocket."""
  notification = Notification.objects.create(
      user=user, kind=kind, text=text, booking=booking, slot=slot
  )
  transaction.on_commit(lambda: _push(notification))
  return notification


def notify_booking_confirmed(booking, promoted=False):
  slot = booking.slot
  if promoted:
    kind = Notification.Kind.PROMOTED
    text = f'Предыдущая запись отменена, ваша запись подтверждена: {slot}'
  else:
    kind = Notification.Kind.CONFIRMED
    text = f'Ваша запись подтверждена: {slot}'
  notify_user(booking.client.user, kind, text, booking=booking, slot=slot)


def _push(notification):
  try:
    layer = get_channel_layer()
    if layer is None:
      return
    from .serializers import NotificationSerializer  # избегаем цикла импортов

    data = dict(NotificationSerializer(notification).data)
    async_to_sync(layer.group_send)(
        user_group(notification.user_id),
        {'type': 'notification.new', 'data': data},
    )
  except Exception:  # недоступный Redis не должен ронять HTTP-запрос
    logger.exception('Failed to push notification %s', notification.pk)