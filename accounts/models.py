from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.utils import timezone


class User(AbstractUser):
    class Meta:
        db_table = 'auth_user'

