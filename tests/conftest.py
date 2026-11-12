import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from curetrack import create_app  # noqa: E402
from curetrack.config import Config  # noqa: E402


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test"


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, username):
    return client.post("/login", data={"username": username, "password": "demo123"})
