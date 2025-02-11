from dartfx.uscensus import UsCensusApi, UsCensusCatalog
from dotenv import load_dotenv
from pathlib import Path
import pytest
from requests_cache import CachedSession

@pytest.fixture(scope="session", autouse=True)
def load_env():
    dotenv_path = Path(__file__).parent / "../.env"  # Construct path from current test file dir
    load_dotenv(dotenv_path=dotenv_path)

@pytest.fixture(scope="session")
def tests_dir():
    return Path(__file__).parent
    
@pytest.fixture(scope="session")
def api():
    return UsCensusApi(session=CachedSession(Path(__file__).parent / "http_cache.sqlite", backend="sqlite"))

@pytest.fixture(scope="session", autouse=True)
def catalog(api):
    return UsCensusCatalog(api)

