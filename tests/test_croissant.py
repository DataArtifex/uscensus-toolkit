import json
import os


def test_acs2023_croissant(catalog, tests_dir):
    dataset = catalog.datasets.get("ACSPUMS1Y2023")
    metadata = dataset.get_croissant()
    assert metadata
    with open(os.path.join(tests_dir, "ACSPUMS1Y2023.croissant.json"), "w") as f:
        json.dump(metadata.to_json(), f, indent=4, default=str)
    print(metadata.issues.report())
