def test_load_catalog(catalog):
    assert catalog


def test_datasets(catalog):
    assert len(catalog.datasets) > 1500


def test_stats(catalog):
    assert catalog.stats
    print(catalog.stats)
    assert catalog.stats.get("n_datasets", 0) > 0
    assert catalog.stats.get("n_aggregate", 0) > 0
    assert catalog.stats.get("n_microdata", 0) > 0
    assert catalog.stats.get("n_timeseries", 0) > 0


def test_search_datasets(catalog):
    datasets = catalog.search_datasets()
    assert len(datasets) > 1500
    microdata_datasets = catalog.search_datasets(is_microdata=True)
    assert len(microdata_datasets) == catalog.stats.get("n_microdata")
    aggregate_datasets = catalog.search_datasets(is_aggregate=True)
    assert len(aggregate_datasets) == catalog.stats.get("n_aggregate")
