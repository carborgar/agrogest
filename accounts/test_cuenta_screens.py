import pytest
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.urls import reverse

from accounts.models import Notification, NotificationPreferences, Organization

User = get_user_model()


@pytest.fixture
def user(db):
    org = Organization.objects.create(name='Org cuenta')
    return User.objects.create_user(username='ana', password='pw12345678', email='ana@example.com', organization=org)


@pytest.mark.django_db
def test_login_anonimo_conserva_formulario_y_next(client):
    html = client.get(reverse('accounts:login') + '?next=/gastos/').content.decode()
    assert 'name="username"' in html and 'name="password"' in html
    assert 'name="next" type="hidden" value="/gastos/"' in html
    assert 'Por favor, inicie sesión para ver esta página.' in html
    assert '<style' not in html.split('</head>')[1]


@pytest.mark.django_db
def test_login_error_muestra_credenciales_incorrectas(client, user):
    r = client.post(reverse('accounts:login'), {'username': 'ana', 'password': 'mal'})
    assert r.status_code == 200
    assert 'Credenciales incorrectas' in r.content.decode()


@pytest.mark.django_db
def test_login_correcto_respeta_next(client, user):
    r = client.post(reverse('accounts:login'), {'username': 'ana', 'password': 'pw12345678', 'next': '/gastos/'})
    assert r.status_code == 302 and r.url == '/gastos/'


@pytest.mark.django_db
def test_recuperar_contraseña_pantallas(client):
    assert 'id="id_email"' in client.get(reverse('accounts:password_reset')).content.decode()
    assert 'Email enviado' in client.get(reverse('accounts:password_reset_done')).content.decode()
    assert 'Contraseña cambiada' in client.get(reverse('accounts:password_reset_complete')).content.decode()
    r = client.get(reverse('accounts:password_reset_confirm', args=['MQ', 'x-y']))
    assert 'Enlace no válido' in r.content.decode()


@pytest.mark.django_db
def test_recuperar_contraseña_error_de_campo(client):
    r = client.post(reverse('accounts:password_reset'), {'email': 'no-es-email'})
    html = r.content.decode()
    assert 'Por favor corrige los errores indicados.' in html and 'tf-err' in html


@pytest.mark.django_db
def test_inbox_vacio_y_con_nuevas(client, user):
    client.force_login(user)
    assert 'No tienes notificaciones todavía' in client.get(reverse('accounts:notification-inbox')).content.decode()

    Notification.objects.create(user=user, event_type='treatment_created', title='Nuevo A', link='/tratamientos/')
    Notification.objects.create(user=user, event_type='treatment_finished', title='Fin B', read=True)
    r = client.get(reverse('accounts:notification-inbox'))
    html = r.content.decode()
    assert r.context['new_count'] == 1
    assert '1 nueva' in html
    assert html.count('nt-new') == 1 and 'Ver detalle' in html
    # al abrir quedan leídas
    assert r.wsgi_request.user.notifications.filter(read=False).count() == 0
    assert r.context['new_count'] == 1
    assert client.get(reverse('accounts:notification-inbox')).context['new_count'] == 0


@pytest.mark.django_db
def test_preferencias_marca_canal_y_guarda(client, user):
    client.force_login(user)
    NotificationPreferences.objects.update_or_create(user=user, defaults={'treatment_finished_channel': 'both'})
    html = client.get(reverse('accounts:notification-preferences')).content.decode()
    assert 'id="tfc_both"' in html and 'value="both" checked' in html
    r = client.post(reverse('accounts:notification-preferences'),
                    {'treatment_created_channel': 'email', 'treatment_finished_channel': 'none'})
    assert r.status_code == 302
    prefs = NotificationPreferences.objects.get(user=user)
    assert (prefs.treatment_created_channel, prefs.treatment_finished_channel) == ('email', 'none')


@pytest.mark.django_db
def test_landing_publica_y_errores_renderizan(client):
    r = client.get('/')
    assert r.status_code == 200
    html = r.content.decode()
    assert f'href="{reverse("accounts:login")}"' in html and '>Entrar</a>' in html
    assert '<title>AgroGest</title>' in html and '<meta name="robots" content="noindex">' in html
    assert 'Proyecto de' in html and 'class="lp' not in html
    assert 'linear-gradient' not in html and '<style' not in html
    assert '404' in render_to_string('404.html') and '500' in render_to_string('500.html')


@pytest.mark.django_db
def test_landing_con_sesion_va_a_la_app(client, user):
    client.force_login(user)
    r = client.get('/')
    assert r.status_code == 302 and r.url == reverse('field_list')


@pytest.mark.django_db
@pytest.mark.parametrize('destino', ['https://evil.com', '//evil.com', 'https:evil.com'])
def test_login_no_redirige_a_hosts_externos(client, user, destino):
    r = client.post(reverse('accounts:login'), {'username': 'ana', 'password': 'pw12345678', 'next': destino})
    assert r.status_code == 302 and r.url == reverse('home')
    client.force_login(user)
    r = client.get(reverse('accounts:login') + '?next=' + destino)
    assert r.status_code == 302 and r.url == reverse('home')


@pytest.mark.django_db
def test_login_anonimo_no_reinyecta_next_externo(client):
    html = client.get(reverse('accounts:login') + '?next=//evil.com').content.decode()
    assert 'evil.com' not in html


@pytest.mark.django_db
def test_errores_404_y_500_con_sufijo_y_handler_real(client, rf):
    from django.views.defaults import server_error
    assert '<title>Página no encontrada · AgroGest</title>' in client.get('/no-existe-xyz/').content.decode()
    r = server_error(rf.get('/'))
    assert r.status_code == 500
    assert '<title>Error del servidor · AgroGest</title>' in r.content.decode()
