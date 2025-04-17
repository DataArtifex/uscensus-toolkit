


def test_acs2023_geography(acs2023):
    dataset = acs2023
    print(dataset.stats)
    assert dataset
    assert dataset.geography
    print(dataset.geography)
    assert len(dataset.geography.fips) == 4
    
def test_acs2023_variables(acs2023):
    dataset = acs2023
    print(dataset.stats)
    assert dataset
    assert dataset.variables
    var = dataset.variables.get("HHLANP")
    assert len(var.codelist) >= 130
    
