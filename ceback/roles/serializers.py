from rest_framework import serializers

from .models import Booking, Client, Doctor, Manager, Notification, Slot
from .permissions import is_doctor, is_manager
from .realtime import slot_queue

MAX_BOOKINGS_PER_SLOT = 10


class ManagerOnlyFieldsMixin:
  """Поля из manager_only_fields становятся read-only для не-менеджеров."""

  manager_only_fields = ()

  def get_fields(self):
    fields = super().get_fields()
    request = self.context.get('request')
    if request is not None and not is_manager(request.user):
      for name in self.manager_only_fields:
        if name in fields:
          fields[name].read_only = True
    return fields


class ClientSerializer(ManagerOnlyFieldsMixin, serializers.ModelSerializer):
  manager_only_fields = ('user',)

  class Meta:
    model = Client
    fields = ['id', 'user', 'phone', 'email', 'full_name', 'created_at']
    read_only_fields = ['created_at']


class DoctorSerializer(ManagerOnlyFieldsMixin, serializers.ModelSerializer):
  manager_only_fields = ('user', 'is_active')

  class Meta:
    model = Doctor
    fields = ['id', 'user', 'specialization', 'phone', 'is_active', 'full_name']


class ManagerSerializer(serializers.ModelSerializer):
  class Meta:
    model = Manager
    fields = [
        'id', 'user', 'full_name', 'phone', 'department', 'is_active',
        'created_at',
    ]
    read_only_fields = ['created_at']


class SlotSerializer(ManagerOnlyFieldsMixin, serializers.ModelSerializer):
  bookings_count = serializers.SerializerMethodField()
  is_available = serializers.SerializerMethodField()
  doctor_name = serializers.CharField(source='doctor.full_name', read_only=True)
  queue = serializers.SerializerMethodField()

  class Meta:
    model = Slot
    fields = [
        'id', 'doctor', 'doctor_name', 'slot_date', 'start_time', 'end_time',
        'slot_state', 'bookings_count', 'is_available', 'queue',
    ]

  def get_queue(self, obj):
    """Топ-10 клиентов слота: только в detail и только менеджеру/врачу слота."""
    view = self.context.get('view')
    request = self.context.get('request')
    if view is None or request is None:
      return None
    if getattr(view, 'action', None) != 'retrieve':
      return None
    user = request.user
    if is_manager(user) or (is_doctor(user) and obj.doctor.user_id == user.id):
      return slot_queue(obj)
    return None

  def get_bookings_count(self, obj):
    value = getattr(obj, 'bookings_count', None)
    return value if value is not None else obj.Bookings.count()

  def get_is_available(self, obj):
    return (
        obj.slot_state in (Slot.SlotState.FREE, Slot.SlotState.BOOKED)
        and self.get_bookings_count(obj) < MAX_BOOKINGS_PER_SLOT
    )

  def validate(self, attrs):
    start = attrs.get('start_time', getattr(self.instance, 'start_time', None))
    end = attrs.get('end_time', getattr(self.instance, 'end_time', None))
    if start and end and end <= start:
      raise serializers.ValidationError(
          {'end_time': 'Время окончания должно быть позже начала.'}
      )

    state = attrs.get('slot_state')
    request = self.context.get('request')
    if state and request is not None and not is_manager(request.user):
      # Врач может только освобождать или блокировать свои слоты.
      if state not in (Slot.SlotState.FREE, Slot.SlotState.BLOCKED):
        raise serializers.ValidationError(
            {'slot_state': 'Доступны только состояния Free и Blocked.'}
        )
      if (
          state == Slot.SlotState.FREE
          and self.instance is not None
          and self.instance.Bookings.exists()
      ):
        raise serializers.ValidationError(
            {'slot_state': 'На слоте есть букинги, его нельзя сделать Free.'}
        )
    return attrs


class BookingSerializer(serializers.ModelSerializer):
  client_name = serializers.CharField(source='client.full_name', read_only=True)
  slot_info = serializers.CharField(source='slot', read_only=True)
  position = serializers.IntegerField(read_only=True)  # место в очереди слота

  class Meta:
    model = Booking
    fields = [
        'id', 'client', 'client_name', 'slot', 'slot_info', 'is_confirmed',
        'position', 'created_at',
    ]
    # is_confirmed меняется только через логику (первый букинг / confirm).
    read_only_fields = ['is_confirmed', 'created_at']


class NotificationSerializer(serializers.ModelSerializer):
  class Meta:
    model = Notification
    fields = ['id', 'kind', 'text', 'booking', 'slot', 'is_read', 'created_at']
    read_only_fields = fields