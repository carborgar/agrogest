import pytest
from django.contrib.auth import get_user_model

from farm.tests.factories import OrganizationFactory


@pytest.fixture
def org(db):
    return OrganizationFactory(name='Explotación')


@pytest.fixture
def user(org):
    return get_user_model().objects.create_user('carlos', 'c@example.com', 'x', organization=org)


@pytest.fixture
def ctx(user, org):
    from datetime import date

    from assistant.tools import ToolContext
    return ToolContext(user=user, organization=org, today=date(2026, 11, 4))


@pytest.fixture
def settings_assistant(settings):
    settings.ASSISTANT_API_KEY = 'clave'
    settings.ASSISTANT_DAILY_QUESTIONS = 5
    settings.ASSISTANT_DAILY_CALLS = 10
    settings.ASSISTANT_TIMEOUT = 25
    settings.ASSISTANT_MODEL = 'modelo-a,modelo-b'
    return settings
