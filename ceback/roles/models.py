from django.contrib.auth.models import User
from django.db import models


class Client(models.Model):
  user = models.OneToOneField(
      User, on_delete=models.CASCADE, verbose_name='User'
  )
  phone = models.CharField(
      max_length=20, unique=True, verbose_name='Phone', blank=True, null=True
  )
  email = models.EmailField(
      blank=True, null=True, verbose_name='Email'
  )
  created_at = models.DateTimeField(
      auto_now_add=True, verbose_name='Creation Date'
  )
  full_name = models.CharField(max_length=310, verbose_name='Full Name', blank=True, null=True, default="No Name")

  class Meta:
    verbose_name = 'Client'
    verbose_name_plural = 'Clients'

  def __str__(self):
    return self.full_name


class Doctor(models.Model):
  user = models.OneToOneField(
      User, on_delete=models.CASCADE, verbose_name='User'
  )
  specialization = models.CharField(
      max_length=255, verbose_name='Specialization'
  )
  phone = models.CharField(max_length=20, verbose_name='Phone', blank=True, null=True)
  is_active = models.BooleanField(default=True, verbose_name='Is Active')
  full_name = models.CharField(max_length=310, verbose_name='Full Name', blank=True, null=True, default="No Name")

  class Meta:
    verbose_name = 'Doctor'
    verbose_name_plural = 'Doctors'

  def __str__(self):
    return f'{self.full_name} ({self.specialization})'


class Manager(models.Model):
  user = models.OneToOneField(
      User, on_delete=models.CASCADE, verbose_name='User'
  )
  full_name = models.CharField(max_length=255, verbose_name='Full name')
  phone = models.CharField(max_length=20, unique=True, verbose_name='Phone')
  department = models.CharField(
      max_length=100, blank=True, null=True, verbose_name='Department / Job title'
  )
  is_active = models.BooleanField(default=True, verbose_name='Active')
  created_at = models.DateTimeField(
      auto_now_add=True, verbose_name='Creation time'
  )

  class Meta:
    verbose_name = 'Manager'
    verbose_name_plural = 'Managers'

  def __str__(self):
    return f'Manager: {self.full_name}'



class Slot(models.Model):

  class SlotState(models.TextChoices):
    FREE = 'Free', 'Free'
    HELD = 'Held', 'Held'
    BOOKED = 'Booked', 'Booked'
    BLOCKED = 'Blocked', 'Blocked'

  doctor = models.ForeignKey(
      Doctor,
      on_delete=models.CASCADE,
      related_name='Slots',
      verbose_name='Doctor',
  )
  slot_date = models.DateField(verbose_name='Slot Date')
  start_time = models.TimeField(verbose_name='Start Time')
  end_time = models.TimeField(verbose_name='End Time')
  slot_state = models.CharField(
      max_length=20,
      choices=SlotState.choices,
      default=SlotState.FREE,
      verbose_name='Slot Status',
  )

  class Meta:
    unique_together = ('doctor', 'slot_date', 'start_time')
    verbose_name = 'Slot'
    verbose_name_plural = 'Slots'

  def __str__(self):
    return (
        f'{self.doctor.full_name} | {self.slot_date} {self.start_time} -'
        f' {self.end_time} [{self.slot_state}]'
    )


class Booking(models.Model):
  client = models.ForeignKey(
      Client,
      on_delete=models.CASCADE,
      related_name='bookings',
      verbose_name='Client',
  )
  slot = models.ForeignKey(
      Slot,
      on_delete=models.CASCADE,
      related_name='Bookings',
      verbose_name='Slot',
  )
  created_at = models.DateTimeField(
      auto_now_add=True, verbose_name='Book Date'
  )

  class Meta:
    unique_together = ('client', 'slot')
    verbose_name = 'Booking'
    verbose_name_plural = 'Bookings'

  def __str__(self):
    return f'Book #{self.id} - {self.client.full_name} for {self.slot}'