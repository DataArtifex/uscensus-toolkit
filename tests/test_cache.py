def test_24hour_cache_expiration(api):
    print(api._session.settings)
    assert api._session.settings.urls_expire_after["api.census.gov"] == 24 * 60 * 60
