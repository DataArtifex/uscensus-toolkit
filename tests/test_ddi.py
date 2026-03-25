import os
from xml.dom import minidom

import pytest
from lxml import etree as ET  # type: ignore[import-untyped]


@pytest.fixture
def ddi_schema(tests_dir):
    xml_schema_doc = ET.parse(os.path.join(tests_dir, "ddi_2_5_1/schemas", "codebook.xsd"))
    xml_schema = ET.XMLSchema(xml_schema_doc)
    return xml_schema


def test_acs2023_ddi_codebook(catalog, tests_dir, ddi_schema):
    dataset = catalog.datasets.get("ACSPUMS1Y2023")
    xml_str = dataset.get_ddi_codebook()
    assert xml_str
    # save to file (pretty printed)
    with open(os.path.join(tests_dir, "ACSPUMS1Y2023.ddic.xml"), "w") as f:
        dom = minidom.parseString(xml_str)
        f.write(dom.toprettyxml())
    # validate codebook
    xml_doc = ET.fromstring(xml_str)
    ddi_schema.assertValid(xml_doc)
