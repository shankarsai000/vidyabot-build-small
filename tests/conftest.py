import pytest
import tempfile
import os
from backend.config import settings
from backend.database import init_db, close_db

@pytest.fixture(autouse=True, scope="function")
def setup_test_db():
    """Set up a temporary clean database for each test."""
    close_db()
    fd, temp_db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    orig_db_path = settings.DB_PATH
    settings.DB_PATH = temp_db_path
    init_db()
    yield
    close_db()
    try:
        os.remove(temp_db_path)
    except OSError:
        pass
    settings.DB_PATH = orig_db_path
