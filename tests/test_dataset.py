

def test_acs2023_variables(catalog):
    dataset = catalog.datasets.get("ACSPUMS1Y2023")
    print(dataset.stats)
    assert dataset
    assert dataset.variables
    var = dataset.variables.get("HHLANP")
    assert len(var.codelist) >= 130
    
