
def test_load_catalog(catalog):
    assert catalog

def test_get_datasets(catalog):
    assert catalog.datasets
    assert len(catalog.datasets) > 1000

def test_stats(catalog):
    print(catalog.stats)
    assert catalog.stats
    assert catalog.stats.get("n_datasets",0) > 0
    assert catalog.stats.get("n_aggregate",0) > 0
    assert catalog.stats.get("n_microdata",0) > 0
    assert catalog.stats.get("n_timeseries",0) > 0