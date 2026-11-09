import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from .models import Slot

logger = logging.getLogger(__name__)


def public_group(slot_id):
  return f'slot_{slot_id}'


def staff_group(slot_id):
  return f'slot_{slot_id}_staff'


def slot_queue(slot, limit=10):
  """Топ-N букингов слота по времени записи (позиция 1 = самый первый)."""
  bookings = (
      slot.Bookings.select_related('client').order_by('created_at', 'id')[:limit]
  )
  return [
      {
          'position': position,
          'booking_id': b.id,
          'client_id': b.client_id,
          'client_name': b.client.full_name,
          'is_confirmed': b.is_confirmed,
          'created_at': b.created_at.isoformat(),
      }
      for position, b in enumerate(bookings, start=1)
  ]


def slot_snapshot(slot_id, staff=False):
  """Состояние слота. Очередь (с именами клиентов) только для staff."""
  from .serializers import MAX_BOOKINGS_PER_SLOT  # избегаем циклического импорта

  try:
    slot = Slot.objects.get(pk=slot_id)
  except Slot.DoesNotExist:
    return None

  count = slot.Bookings.count()
  data = {
      'id': slot.pk,
      'slot_state': slot.slot_state,
      'bookings_count': count,
      'is_available': (
          slot.slot_state in (Slot.SlotState.FREE, Slot.SlotState.BOOKED)
          and count < MAX_BOOKINGS_PER_SLOT
      ),
  }
  if staff:
    data['queue'] = slot_queue(slot)
  return data


def notify_slot(slot_id):
  """Рассылает обновление слота подписчикам после коммита транзакции."""

  def _send():
    try:
      layer = get_channel_layer()
      if layer is None:
        return
      for group, staff in (
          (public_group(slot_id), False),
          (staff_group(slot_id), True),
      ):
        data = slot_snapshot(slot_id, staff=staff) or {
            'id': slot_id,
            'deleted': True,
        }
        async_to_sync(layer.group_send)(
            group, {'type': 'slot.update', 'data': data}
        )
    except Exception:  # недоступный Redis не должен ронять HTTP-запрос
      logger.exception('Failed to broadcast slot %s update', slot_id)

  transaction.on_commit(_send)