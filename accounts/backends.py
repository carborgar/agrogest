from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailOrUsernameModelBackend(ModelBackend):
    """
    Backend de autenticación que permite iniciar sesión con nombre de usuario o email.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()

        if username is None or password is None:
            return None

        # Intentar buscar el usuario por username o email
        try:
            user = UserModel.objects.get(username__iexact=username)
        except UserModel.DoesNotExist:
            try:
                user = UserModel.objects.get(email__iexact=username)
            except UserModel.DoesNotExist:
                UserModel().set_password(password)  # mitigación de timing attack
                return None
            except UserModel.MultipleObjectsReturned:
                return None
        except UserModel.MultipleObjectsReturned:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None
