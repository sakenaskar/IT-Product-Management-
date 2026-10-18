from django.dispatch import receiver
from allauth.account.signals import user_signed_up
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Client, Doctor

@receiver(user_signed_up)
def handle_user_signed_up(request, sociallogin, user, **kwargs):
    # grab the user's data
    new_user_data = sociallogin.account.extra_data
    print(new_user_data)
    # perform tasks/processing on data

@receiver(post_save, sender=User)
def create_client_profile(sender, instance, created, **kwargs):
  """Create client with user"""
  if created:
    Client.objects.create(
        user=instance,
        full_name=f'{instance.first_name} {instance.last_name}'.strip()
        or instance.username,
        phone=(
            f'temp_{instance.id}'
        ),
        email=instance.email,
    )

"""
@receiver(post_save, sender=Doctor)
def create_user_for_doctor(sender, instance, created, **kwargs):
  #Create new user when creating doctor
  if created and not instance.user_id:
    username = f'doctor_{instance.id}'

    user = User.objects.create_user(
        username=username,
        first_name=instance.full_name.split()[
            1
        ],
        last_name=instance.full_name.split()[0]
    )
    user.set_password('temporary_password_123')
    user.save()

    Doctor.objects.filter(pk=instance.pk).update(user=user)
"""

@receiver(post_save, sender=User)
def save_client_profile(sender, instance, **kwargs):
  """Сохраняет профиль Client при обновлении User (если он существует)."""
  if hasattr(instance, 'client'):
    instance.client.save()