from django.db import IntegrityError, transaction
from django.db.models import Count, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Booking, Client, Doctor, Manager, Notification, Slot
from .notifications import notify_booking_confirmed, notify_user
from .permissions import (
    IsClient, IsDoctor, IsManager, is_client, is_doctor, is_manager,
)
from .realtime import notify_slot
from .serializers import (
    MAX_BOOKINGS_PER_SLOT, BookingSerializer, ClientSerializer,
    DoctorSerializer, ManagerSerializer, NotificationSerializer,
    SlotSerializer,
)

SlotState = Slot.SlotState


# ---------------------------------------------------------------------------
# Сервисные функции
# ---------------------------------------------------------------------------

def sync_slot(slot, promoted=False):
  """Приводит слот и его букинги в согласованное состояние.

  - Если подтверждённого букинга нет, подтверждается самый ранний.
  - Free <-> Booked переключается по наличию букингов.
  - Held и Blocked не трогаем.
  Вызывать внутри transaction.atomic() при заблокированном слоте.
  """
  bookings = slot.Bookings.order_by('created_at', 'id')
  first = bookings.first()

  if first is None:
    if slot.slot_state == SlotState.BOOKED:
      slot.slot_state = SlotState.FREE
      slot.save(update_fields=['slot_state'])
    return

  if not bookings.filter(is_confirmed=True).exists():
    try:
      with transaction.atomic():
        first.is_confirmed = True
        first.save(update_fields=['is_confirmed'])
    except IntegrityError:
      pass  # другой запрос уже подтвердил букинг, этот остаётся в очереди
    else:
      notify_booking_confirmed(first, promoted=promoted)

  if slot.slot_state == SlotState.FREE:
    slot.slot_state = SlotState.BOOKED
    slot.save(update_fields=['slot_state'])


class RoleActionPermissionsMixin:
  """permission_map: {action: [PermissionClass, ...]}, 'default' как запасной."""

  permission_map = {}

  def get_permissions(self):
    classes = self.permission_map.get(
        self.action, self.permission_map.get('default', [IsManager])
    )
    return [IsAuthenticated()] + [cls() for cls in classes]


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class ClientViewSet(RoleActionPermissionsMixin, viewsets.ModelViewSet):
  serializer_class = ClientSerializer
  permission_map = {
      'list': [IsManager | IsClient],
      'retrieve': [IsManager | IsClient],
      'update': [IsManager | IsClient],
      'partial_update': [IsManager | IsClient],
      'create': [IsManager],
      'destroy': [IsManager],
  }

  def get_queryset(self):
    qs = Client.objects.select_related('user').order_by('id')
    user = self.request.user
    if is_manager(user):
      return qs
    return qs.filter(user=user)  # клиент видит только себя


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------

class DoctorViewSet(RoleActionPermissionsMixin, viewsets.ModelViewSet):
  serializer_class = DoctorSerializer
  permission_map = {
      'list': [IsAuthenticated],
      'retrieve': [IsAuthenticated],
      'update': [IsManager | IsDoctor],
      'partial_update': [IsManager | IsDoctor],
      'create': [IsManager],
      'destroy': [IsManager],
  }

  def get_queryset(self):
    qs = Doctor.objects.select_related('user').order_by('id')
    user = self.request.user
    if is_manager(user):
      return qs
    if self.action in ('update', 'partial_update'):
      return qs.filter(user=user)  # врач правит только себя
    return qs.filter(is_active=True)


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class ManagerViewSet(viewsets.ModelViewSet):
  queryset = Manager.objects.select_related('user').order_by('id')
  serializer_class = ManagerSerializer
  permission_classes = [IsAuthenticated, IsManager]


# ---------------------------------------------------------------------------
# Slot
# ---------------------------------------------------------------------------

class SlotViewSet(RoleActionPermissionsMixin, viewsets.ModelViewSet):
  serializer_class = SlotSerializer
  permission_map = {
      'list': [IsAuthenticated],
      'retrieve': [IsAuthenticated],
      'create': [IsManager | IsDoctor],
      'update': [IsManager | IsDoctor],
      'partial_update': [IsManager | IsDoctor],
      'destroy': [IsManager | IsDoctor],
      'bookings': [IsManager | IsDoctor],
  }

  def get_queryset(self):
    user = self.request.user
    qs = (
        Slot.objects.select_related('doctor')
        .annotate(bookings_count=Count('Bookings'))
        .order_by('slot_date', 'start_time', 'id')
    )

    if is_manager(user):
      pass
    elif is_doctor(user):
      qs = qs.filter(doctor__user=user)
    else:  # клиент: только будущие незаблокированные слоты активных врачей
      qs = qs.filter(
          slot_state__in=[SlotState.FREE, SlotState.BOOKED],
          slot_date__gte=timezone.localdate(),
          doctor__is_active=True,
      )

    params = self.request.query_params
    if params.get('doctor'):
      qs = qs.filter(doctor_id=params['doctor'])
    if params.get('date'):
      qs = qs.filter(slot_date=params['date'])
    if params.get('date_from'):
      qs = qs.filter(slot_date__gte=params['date_from'])
    if params.get('date_to'):
      qs = qs.filter(slot_date__lte=params['date_to'])
    if params.get('state'):
      qs = qs.filter(slot_state=params['state'])
    if params.get('available') in ('1', 'true', 'True'):
      qs = qs.filter(
          slot_state__in=[SlotState.FREE, SlotState.BOOKED],
          bookings_count__lt=MAX_BOOKINGS_PER_SLOT,
      )
    return qs

  def get_serializer(self, *args, **kwargs):
    # Врач всегда работает только со своими слотами: подставляем doctor.
    data = kwargs.get('data')
    user = self.request.user
    if data is not None and not is_manager(user) and is_doctor(user):
      data = data.copy()
      data['doctor'] = user.doctor.pk
      kwargs['data'] = data
    return super().get_serializer(*args, **kwargs)

  def perform_destroy(self, instance):
    if not is_manager(self.request.user) and instance.Bookings.exists():
      raise ValidationError('Нельзя удалить слот, на котором есть букинги.')
    slot_id = instance.pk
    instance.delete()
    notify_slot(slot_id)

  def perform_create(self, serializer):
    slot = serializer.save()
    notify_slot(slot.pk)

  def perform_update(self, serializer):
    slot = serializer.save()
    notify_slot(slot.pk)

  @action(detail=True, methods=['get'])
  def bookings(self, request, pk=None):
    """Все букинги слота (до 10) — для менеджера и врача слота."""
    slot = self.get_object()
    qs = (
        slot.Bookings.select_related('client', 'slot__doctor')
        .order_by('created_at', 'id')
    )
    return Response(BookingSerializer(qs, many=True).data)


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------

class BookingViewSet(RoleActionPermissionsMixin, viewsets.ModelViewSet):
  serializer_class = BookingSerializer
  permission_map = {
      'list': [IsManager | IsDoctor | IsClient],
      'retrieve': [IsManager | IsDoctor | IsClient],
      'create': [IsManager | IsClient],
      'update': [IsManager],
      'partial_update': [IsManager],
      'destroy': [IsManager | IsClient],
      'confirm': [IsManager],
      'cancel': [IsClient],
      'my': [IsClient],
  }

  def get_queryset(self):
    user = self.request.user
    # позиция в очереди слота: 1 = самый первый
    earlier = (
        Booking.objects.filter(slot=OuterRef('slot'))
        .filter(
            Q(created_at__lt=OuterRef('created_at'))
            | Q(created_at=OuterRef('created_at'), id__lt=OuterRef('id'))
        )
        .order_by()
        .values('slot')
        .annotate(c=Count('id'))
        .values('c')
    )
    qs = (
        Booking.objects.select_related('client', 'slot__doctor')
        .annotate(
            position=Coalesce(
                Subquery(earlier, output_field=IntegerField()), Value(0)
            )
            + 1
        )
        .order_by('slot__slot_date', 'slot__start_time', 'created_at', 'id')
    )

    if is_manager(user):
      pass
    elif is_doctor(user):
      qs = qs.filter(slot__doctor__user=user)
    else:
      qs = qs.filter(client__user=user)

    params = self.request.query_params
    if params.get('slot'):
      qs = qs.filter(slot_id=params['slot'])
    if params.get('client') and is_manager(user):
      qs = qs.filter(client_id=params['client'])
    if params.get('confirmed') in ('1', 'true', 'True'):
      qs = qs.filter(is_confirmed=True)
    return qs

  def get_serializer(self, *args, **kwargs):
    # Клиент всегда бронирует от своего имени.
    data = kwargs.get('data')
    user = self.request.user
    if (
        data is not None
        and self.action == 'create'
        and not is_manager(user)
        and is_client(user)
    ):
      data = data.copy()
      data['client'] = user.client.pk
      kwargs['data'] = data
    return super().get_serializer(*args, **kwargs)

  # --- create: первый букинг подтверждается автоматически, максимум 10 ---
  def create(self, request, *args, **kwargs):
    serializer = self.get_serializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    slot_id = serializer.validated_data['slot'].pk

    with transaction.atomic():
      slot = Slot.objects.select_for_update().get(pk=slot_id)

      if slot.slot_state not in (SlotState.FREE, SlotState.BOOKED):
        raise ValidationError({'slot': 'Слот недоступен для записи.'})

      if not is_manager(request.user):
        now = timezone.localtime()
        if (slot.slot_date, slot.start_time) < (now.date(), now.time()):
          raise ValidationError({'slot': 'Слот уже в прошлом.'})

      if slot.Bookings.count() >= MAX_BOOKINGS_PER_SLOT:
        raise ValidationError(
            {'slot': f'На слот уже {MAX_BOOKINGS_PER_SLOT} букингов.'}
        )

      booking = serializer.save()
      sync_slot(slot)  # первый букинг -> is_confirmed, слот -> Booked
      notify_slot(slot.pk)

    booking.refresh_from_db()
    return Response(
        self.get_serializer(booking).data, status=status.HTTP_201_CREATED
    )

  # --- update (менеджер): смена клиента/слота с пересинхронизацией ---
  def perform_update(self, serializer):
    old_slot_id = serializer.instance.slot_id
    new_slot = serializer.validated_data.get('slot')
    new_slot_id = new_slot.pk if new_slot else old_slot_id

    with transaction.atomic():
      slots = {
          s.pk: s
          for s in Slot.objects.select_for_update()
          .filter(pk__in={old_slot_id, new_slot_id})
          .order_by('pk')
      }

      if new_slot_id != old_slot_id:
        target = slots[new_slot_id]
        if target.Bookings.count() >= MAX_BOOKINGS_PER_SLOT:
          raise ValidationError(
              {'slot': f'На слот уже {MAX_BOOKINGS_PER_SLOT} букингов.'}
          )
        serializer.save(is_confirmed=False)
      else:
        serializer.save()

      for slot in slots.values():
        slot.refresh_from_db()
        sync_slot(slot)
        notify_slot(slot.pk)

  # --- delete: если удалён подтверждённый, подтверждается следующий ---
  def _cancel(self, booking):
    """Удаляет букинг; если он был подтверждён, подтверждается следующий."""
    actor = self.request.user
    with transaction.atomic():
      slot = Slot.objects.select_for_update().get(pk=booking.slot_id)

      if not is_manager(actor):
        now = timezone.localtime()
        if (slot.slot_date, slot.start_time) < (now.date(), now.time()):
          raise ValidationError('Слот уже прошёл, отменить запись нельзя.')

      was_confirmed = booking.is_confirmed
      client_user = booking.client.user
      booking.delete()

      if actor.pk != client_user.pk:  # отменил менеджер: сообщаем клиенту
        notify_user(
            client_user,
            Notification.Kind.CANCELLED,
            f'Ваша запись отменена: {slot}',
            slot=slot,
        )

      sync_slot(slot, promoted=was_confirmed)
      notify_slot(slot.pk)

  def perform_destroy(self, instance):
    self._cancel(instance)

  # --- клиент отменяет свою запись ---
  @action(detail=True, methods=['post'])
  def cancel(self, request, pk=None):
    booking = self.get_object()  # queryset клиента: только свои
    self._cancel(booking)
    return Response(status=status.HTTP_204_NO_CONTENT)

  # --- мои букинги (?upcoming=1 только будущие) ---
  @action(detail=False, methods=['get'])
  def my(self, request):
    qs = self.get_queryset()
    if request.query_params.get('upcoming') in ('1', 'true', 'True'):
      qs = qs.filter(slot__slot_date__gte=timezone.localdate())
    page = self.paginate_queryset(qs)
    if page is not None:
      return self.get_paginated_response(self.get_serializer(page, many=True).data)
    return Response(self.get_serializer(qs, many=True).data)

  # --- менеджер выбирает победителя среди букингов слота ---
  @action(detail=True, methods=['post'])
  def confirm(self, request, pk=None):
    booking = self.get_object()
    with transaction.atomic():
      slot = Slot.objects.select_for_update().get(pk=booking.slot_id)
      was_confirmed = booking.is_confirmed
      previous = (
          slot.Bookings.filter(is_confirmed=True)
          .exclude(pk=booking.pk)
          .select_related('client__user')
          .first()
      )
      slot.Bookings.exclude(pk=booking.pk).update(is_confirmed=False)
      booking = get_object_or_404(
          Booking.objects.select_related('client__user', 'slot'), pk=booking.pk
      )
      booking.is_confirmed = True
      booking.save(update_fields=['is_confirmed'])
      if slot.slot_state != SlotState.BLOCKED:
        slot.slot_state = SlotState.BOOKED
        slot.save(update_fields=['slot_state'])
      if not was_confirmed:
        notify_booking_confirmed(booking)
      if previous is not None:
        notify_user(
            previous.client.user,
            Notification.Kind.REPLACED,
            f'Менеджер выбрал другую запись на слот, ваша осталась в очереди: {slot}',
            booking=previous,
            slot=slot,
        )
      notify_slot(slot.pk)
    return Response(self.get_serializer(booking).data)


# ---------------------------------------------------------------------------
# Notification
# ---------------------------------------------------------------------------

class NotificationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
  """Уведомления текущего пользователя (?unread=1 только непрочитанные)."""

  serializer_class = NotificationSerializer
  permission_classes = [IsAuthenticated]

  def get_queryset(self):
    qs = Notification.objects.filter(user=self.request.user)
    if self.request.query_params.get('unread') in ('1', 'true', 'True'):
      qs = qs.filter(is_read=False)
    return qs

  @action(detail=True, methods=['post'])
  def read(self, request, pk=None):
    notification = self.get_object()
    if not notification.is_read:
      notification.is_read = True
      notification.save(update_fields=['is_read'])
    return Response(self.get_serializer(notification).data)

  @action(detail=False, methods=['post'], url_path='read-all')
  def read_all(self, request):
    updated = Notification.objects.filter(
        user=request.user, is_read=False
    ).update(is_read=True)
    return Response({'updated': updated})

  @action(detail=False, methods=['get'], url_path='unread-count')
  def unread_count(self, request):
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    return Response({'count': count})