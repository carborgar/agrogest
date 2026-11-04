"""Repetir, clonar e instrucciones para el operador: acceso, estados y contenido de la hoja."""
from datetime import date, timedelta

import pytest
from django.urls import reverse

from accounts.models import User
from farm.models import Treatment
from farm.tests.factories import *


def _days(n):
    return date.today() + timedelta(days=n)


@pytest.fixture
def setup(client):
    org = OrganizationFactory()
    user = User.objects.create_user(username='secundarias', password='pass', organization=org)
    client.force_login(user)
    return client, org


def _spraying(org, field=None, products=2, **kwargs):
    field = field or FieldFactory(organization=org, area=2.5)
    machine = MachineFactory(organization=org, capacity=1000)
    t = SprayingTreatmentFactory(organization=org, field=field, machine=machine, water_per_ha=1000,
                                 date=_days(3), **kwargs)
    for i in range(products):
        SprayingTreatmentProductFactory(treatment=t, product=SprayingProductFactory(organization=org), position=i)
    return t


@pytest.mark.django_db
class TestCloneScreen:

    def test_lists_only_other_fields_with_summary_bar(self, setup):
        client, org = setup
        t = _spraying(org)
        otra = FieldFactory(organization=org, name='Borboli')

        response = client.get(reverse('treatment-clone', args=[t.pk]))
        html = response.content.decode()

        assert response.status_code == 200
        assert list(response.context['available_fields']) == [otra]
        assert f'id="field_{otra.pk}"' in html and f'id="field_{t.field.pk}"' not in html
        assert 'Se crearán' in html and 'tf-summary' in html
        assert t.name in html

    def test_without_other_fields_shows_empty_state_and_no_form(self, setup):
        client, org = setup
        t = _spraying(org)

        html = client.get(reverse('treatment-clone', args=[t.pk])).content.decode()

        assert 'No hay otras parcelas' in html
        assert 'id="cloneForm"' not in html
        assert reverse('field-create') in html

    def test_post_clones_into_each_selected_field(self, setup):
        client, org = setup
        t = _spraying(org)
        a = FieldFactory(organization=org, name='Borboli', area=2)
        b = FieldFactory(organization=org, name='Vegueta', area=4)

        response = client.post(reverse('treatment-clone', args=[t.pk]), {
            'field_id': [a.pk, b.pk],
            f'name_{a.pk}': 'Cobre Borboli', f'date_{a.pk}': _days(5).isoformat(),
            f'name_{b.pk}': '', f'date_{b.pk}': '',
        })

        assert response.status_code == 302
        assert Treatment.objects.filter(field=a, name='Cobre Borboli', date=_days(5)).count() == 1
        clon_b = Treatment.objects.get(field=b)
        assert clon_b.name == t.name and clon_b.date == t.date
        assert clon_b.treatmentproduct_set.count() == 2

    def test_post_without_fields_redirects_back_with_error(self, setup):
        client, org = setup
        t = _spraying(org)

        response = client.post(reverse('treatment-clone', args=[t.pk]), {})

        assert response.status_code == 302
        assert response.url == reverse('treatment-clone', args=[t.pk])
        assert Treatment.objects.count() == 1

    def test_other_organization_cannot_clone(self, setup):
        client, org = setup
        otra_org = OrganizationFactory(name='Otra explotación')
        ajeno = _spraying(otra_org)
        mia = FieldFactory(organization=org)

        assert client.get(reverse('treatment-clone', args=[ajeno.pk])).status_code == 404
        response = client.post(reverse('treatment-clone', args=[ajeno.pk]), {'field_id': [mia.pk]})
        assert response.status_code == 404
        assert not Treatment.objects.filter(field=mia).exists()


@pytest.mark.django_db
class TestRepeatScreen:

    def test_page_has_calendar_summary_and_disabled_submit(self, setup):
        client, org = setup
        t = _spraying(org)

        response = client.get(reverse('treatment-repeat', args=[t.pk]))
        html = response.content.decode()

        assert response.status_code == 200
        assert 'id="repeatForm"' in html and 'id="calBody"' in html
        assert 'Se crearán' in html and 'tf-summary' in html
        assert 'disabled id="submitBtn"' in html
        assert f"'{t.date.isoformat()}'" in html  # fecha del original, que no se puede repetir
        assert '.toISOString(' not in html  # fechas siempre en local, nunca en UTC
        assert 'now.getFullYear()' in html and 'now.getDate()' in html

    def test_post_creates_one_treatment_per_date(self, setup):
        client, org = setup
        t = _spraying(org)

        response = client.post(reverse('treatment-repeat', args=[t.pk]),
                               {'dates': [_days(10).isoformat(), _days(17).isoformat()]})

        assert response.status_code == 302
        assert response.url == reverse('treatment-list')
        copias = Treatment.objects.filter(field=t.field).exclude(pk=t.pk)
        assert sorted(c.date for c in copias) == [_days(10), _days(17)]
        assert all(c.treatmentproduct_set.count() == 2 for c in copias)

    def test_post_single_date_goes_to_the_new_detail(self, setup):
        client, org = setup
        t = _spraying(org)

        response = client.post(reverse('treatment-repeat', args=[t.pk]), {'dates': [_days(10).isoformat()]})

        nuevo = Treatment.objects.exclude(pk=t.pk).get()
        assert response.url == reverse('treatment-detail', args=[nuevo.pk])

    def test_post_without_dates_rerenders_with_error(self, setup):
        client, org = setup
        t = _spraying(org)

        response = client.post(reverse('treatment-repeat', args=[t.pk]), {})

        assert response.status_code == 200
        assert 'al menos una fecha' in response.content.decode()
        assert Treatment.objects.count() == 1

    def test_other_organization_gets_404(self, setup):
        client, org = setup
        ajeno = _spraying(OrganizationFactory(name='Otra explotación'))

        assert client.get(reverse('treatment-repeat', args=[ajeno.pk])).status_code == 404


@pytest.mark.django_db
class TestOperatorSheet:

    def _html(self, client, t):
        response = client.get(reverse('treatment-instructions', args=[t.pk]))
        assert response.status_code == 200
        return response.content.decode()

    def test_spraying_lists_full_loads_in_order_and_partial_water(self, setup):
        client, org = setup
        t = _spraying(org)  # 2,5 ha × 1000 L/ha = 2500 L en cubas de 1000 L → 2 llenas + 500 L

        html = self._html(client, t)

        assert 'id="export-container"' in html and 'id="export-pdf"' in html and 'id="export-image"' in html
        assert '2 máquinas completas con:' in html
        assert '+ 1 máquina parcial con 500 L de agua' in html
        assert '2500 L en total' in html
        assert 'Aplica los productos en el orden indicado.' in html
        names = [tp.product.name for tp in t.treatmentproduct_set.all()]
        assert html.index(names[0]) < html.index(names[1])

    def test_sheet_is_self_contained(self, setup):
        client, org = setup
        t = _spraying(org)

        html = self._html(client, t)
        sheet = html[html.index('id="export-container"'):html.index('</article>')]

        assert '<style' not in html and 'style="' not in html
        assert '<i ' not in sheet and 'fa-' not in sheet  # sin iconos: la imagen exportada no depende de la fuente
        assert 'Generado por AgroGest' in sheet

    def test_fertigation_shows_total_doses_without_water(self, setup):
        client, org = setup
        field = FieldFactory(organization=org, area=2)
        t = FertigationTreatmentFactory(organization=org, field=field, date=_days(1))
        FertigationTreatmentProductFactory(treatment=t, product=FertigationProductFactory(organization=org))

        html = self._html(client, t)

        assert 'Dosis a aplicar en toda la parcela:' in html
        assert 'máquina' not in html and 'Mojado' not in html

    def test_spraying_without_machine_falls_back_to_total_quantities(self, setup):
        client, org = setup
        t = SprayingTreatmentFactory(organization=org, field=FieldFactory(organization=org), machine=None, date=_days(2))
        SprayingTreatmentProductFactory(treatment=t, product=SprayingProductFactory(organization=org))

        html = self._html(client, t)

        assert 'Cantidad total para la parcela:' in html

    def test_spraying_that_fits_in_one_machine_shows_total_quantities(self, setup):
        client, org = setup
        field = FieldFactory(organization=org, area=0.5)
        t = _spraying(org, field=field)  # 0,5 ha × 1000 L/ha = 500 L, caben en una cuba de 1000 L

        html = self._html(client, t)

        assert 'Cantidad total para la parcela:' in html
        assert 'máquinas completas' not in html and 'máquina parcial' not in html
        for tp in t.treatmentproduct_set.all():
            assert tp.product.name in html

    def test_other_organization_gets_404(self, setup):
        client, org = setup
        ajeno = _spraying(OrganizationFactory(name='Otra explotación'))

        assert client.get(reverse('treatment-instructions', args=[ajeno.pk])).status_code == 404
