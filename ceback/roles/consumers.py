from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from .models import Notification, Slot
from .notifications import user_group
from .permissions import is_client, is_doctor, is_manager
from .realtime import public_group, slot_snapshot, staff_group


class SlotConsumer(AsyncJsonWebsocketConsumer):
  """ws/slots/<slot_id>/ : живые обновления одного слота.

  Менеджер и врач слота получают очередь (топ-10 клиентов),
  клиенты только состояние и количество букингов.
  """

  async def connect(self):
    self.groups_joined = []
    user = self.scope['user']
    if not user.is_authenticated:
      await self.close(code=4401)
      return

    self.slot_id = int(self.scope['url_route']['kwargs']['slot_id'])
    exists, allowed, staff = await self._check_access(user, self.slot_id)
    if not exists:
      await self.close(code=4404)
      return
    if not allowed:
      await self.close(code=4403)
      return

    self.staff = staff
    group = staff_group(self.slot_id) if staff else public_group(self.slot_id)
    await self.channel_layer.group_add(group, self.channel_name)
    self.groups_joined.append(group)

    await self.accept()
    snapshot = await database_sync_to_async(slot_snapshot)(
        self.slot_id, staff=staff
    )
    await self.send_json(snapshot)

  async def disconnect(self, code):
    for group in getattr(self, 'groups_joined', []):
      await self.channel_layer.group_discard(group, self.channel_name)

  async def receive_json(self, content, **kwargs):
    pass  # канал только на чтение

  async def slot_update(self, event):
    await self.send_json(event['data'])

  @database_sync_to_async
  def _check_access(self, user, slot_id):
    slot = Slot.objects.select_related('doctor').filter(pk=slot_id).first()
    if slot is None:
      return False, False, False

    if is_manager(user):
      return True, True, True
    if is_doctor(user) and slot.doctor.user_id == user.id:
      return True, True, True

    # клиент: те же правила видимости, что и в REST
    visible = (
        is_client(user)
        and slot.slot_state in (Slot.SlotState.FREE, Slot.SlotState.BOOKED)
        and slot.slot_date >= timezone.localdate()
        and slot.doctor.is_active
    )
    return True, visible, False


class NotificationConsumer(AsyncJsonWebsocketConsumer):
  """ws/notifications/ : личные уведомления пользователя в реальном времени."""

  async def connect(self):
    user = self.scope['user']
    if not user.is_authenticated:
      await self.close(code=4401)
      return

    self.group = user_group(user.id)
    await self.channel_layer.group_add(self.group, self.channel_name)
    await self.accept()

    unread = await database_sync_to_async(
        lambda: Notification.objects.filter(user=user, is_read=False).count()
    )()
    await self.send_json({'type': 'unread_count', 'count': unread})

  async def disconnect(self, code):
    if hasattr(self, 'group'):
      await self.channel_layer.group_discard(self.group, self.channel_name)

  async def receive_json(self, content, **kwargs):
    pass  # канал только на чтение

  async def notification_new(self, event):
    await self.send_json({'type': 'notification', 'data': event['data']})