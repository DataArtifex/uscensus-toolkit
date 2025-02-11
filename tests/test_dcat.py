import xml.etree.ElementTree as ET

def test_dcat_json(api):
    data = api.get_dcat_json()
    assert data.get("@context","") == 'https://project-open-data.cio.gov/v1.1/schema/catalog.jsonld'
    assert len(data.get("dataset",[])) > 0

def test_dcat_xml(api):
    xml = api.get_dcat_xml()
    assert type(xml) is ET.Element