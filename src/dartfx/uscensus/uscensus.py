import inspect
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from functools import cached_property
from xml.sax.saxutils import escape

import mlcroissant as mlc
from pydantic import BaseModel, Field, computed_field
from requests_cache import CachedSession

from .__about__ import __version__


def _get_caller_name() -> str:
    """Returns the name of the function that called the current function."""
    frame = inspect.currentframe()
    if frame is None or frame.f_back is None or frame.f_back.f_back is None:
        return "unknown"
    try:
        caller_frame = frame.f_back.f_back  # f_back of the current frame's caller
        return caller_frame.f_code.co_name
    finally:
        # Clean up to avoid reference cycles
        del frame


class UsCensusApiError(Exception):
    """Custom exception for U.S. Census API errors."""

    def __init__(self, message, url, status_code=None, response=None):
        super().__init__(message)
        self.message = message
        self.url = url
        self.status_code = status_code
        self.response = response

    def __str__(self):
        base_message = f"UsCensusApiError: {self.message}"
        base_message += f"; URL: {self.response.url}"
        if self.status_code is not None:
            base_message += f"; Status Code: {self.status_code}"
        return base_message


class UsCensusApi(BaseModel):
    """Helper to call the U.S. Census data API"""

    api_key: str | None = None  # The optional API key
    user_agent: str = f"dartfx-uscensus/{__version__}"
    _session: CachedSession

    def __init__(self, api_key: str | None = None, session: CachedSession | None = None, **kwargs):
        super().__init__(api_key=api_key, **kwargs)  # Call Pydantic's __init__ FIRST
        if session is None:
            self._session = CachedSession(backend="memory")  # create an in-memory session
        else:
            self._session = session
        # set a 24h cache expiration for api.census.gov
        if "api.census.gov" not in self._session.settings.urls_expire_after:
            self._session.settings.urls_expire_after["api.census.gov"] = 24 * 60 * 60

    def request(self, method, path, description=None, content_type="application/json", **kwargs):
        """Call the API."""
        # prepare headers
        default_headers = {"Content-Type": content_type, "User-Agent": self.user_agent}
        if "headers" not in kwargs:
            kwargs["headers"] = {}
        kwargs["headers"] = default_headers | kwargs["headers"]
        # prepare call
        url = f"https://api.census.gov/{path}"
        if "params" not in kwargs:
            kwargs["params"] = {}
        if self.api_key:
            kwargs["params"]["key"] = self.api_key
        # call the API
        response = self._session.request(method, url, **kwargs)
        # handle response
        if response.status_code == 200:
            return response
        else:
            logging.error(f"{description} -- {response.status_code}")
            logging.error(response.text)
            raise UsCensusApiError(description, path, response.status_code, response)

    def get_request(self, path, description=None, headers=None, **kwargs):
        """Call the API using the GET method."""
        headers = headers or {}
        if not description:
            description = _get_caller_name()
        return self.request("get", path, description, headers=headers, **kwargs)

    def post_request(self, path, description=None, **kwargs):
        """Call the API using the POST method."""
        if not description:
            description = _get_caller_name()
        return self.request("post", path, description, **kwargs)

    def get_dcat_json(self) -> dict:
        """Returns the data catalog as a JSON object."""
        response = self.get_request("data.json")
        return response.json()

    def get_dcat_xml(self) -> ET.Element:
        """Returns the data catalog as an XML object."""
        response = self.get_request("data.xml")
        return ET.fromstring(response.text)


class UsCensusCatalog(BaseModel):
    _data: dict
    _datasets: dict[str, "UsCensusDataset"]

    api: UsCensusApi

    def __init__(self, api: UsCensusApi, load_data: bool = True, **kwargs) -> None:
        super().__init__(api=api, **kwargs)  # Call Pydantic's __init__ FIRST
        if load_data:
            self.refresh()
        else:
            self._data = {}
        self._datasets = {}

    def refresh(self):
        self._data = self.api.get_dcat_json()
        self._datasets = {}

    def _get_datasets(self) -> list:
        return self._data.get("dataset", [])

    @property
    def datasets(self) -> dict[str, "UsCensusDataset"]:
        if not self._datasets:
            for dataset in self._get_datasets():
                instance: UsCensusDataset
                if dataset.get("c_isAggregate", False):
                    instance = UsCensusAggregatedDataset(api=self.api, **dataset)
                elif dataset.get("c_isMicrodata", False):
                    instance = UsCensusMicrodataDataset(api=self.api, **dataset)
                elif dataset.get("c_isTimeseries", False):
                    instance = UsCensusTimeSeriesDataset(api=self.api, **dataset)
                else:
                    raise ValueError(f"Unknown dataset type: {dataset.get('identifier')}")
                self._datasets[instance.id] = instance
        return self._datasets

    @property
    def stats(self):
        stats = {
            "n_datasets": 0,
            "n_aggregate": 0,
            "n_aggregate_cube": 0,
            "n_microdata": 0,
            "n_microdata_cube": 0,
            "n_timeseries": 0,
        }
        stats["n_datasets"] = len(self.datasets)
        for dataset in self.datasets.values():
            if dataset.c_isAggregate:
                stats["n_aggregate"] += 1
            if dataset.c_isAggregate and dataset.c_isCube:
                stats["n_aggregate_cube"] += 1
            if dataset.c_isMicrodata:
                stats["n_microdata"] += 1
            if dataset.c_isMicrodata and dataset.c_isCube:
                stats["n_microdata_cube"] += 1
            if dataset.c_isTimeseries:
                stats["n_timeseries"] += 1
        return stats

    def search_datasets(
        self, is_aggregate: bool | None = None, is_cube: bool | None = None, is_microdata: bool | None = None
    ) -> list["UsCensusDataset"]:
        """Search for datasets."""
        datasets = []
        for dataset in self.datasets.values():
            if is_aggregate is not None and dataset.c_isAggregate != is_aggregate:
                continue
            if is_cube is not None and dataset.c_isCube != is_cube:
                continue
            if is_microdata is not None and dataset.c_isMicrodata != is_microdata:
                continue
            datasets.append(dataset)
        return datasets

    def get_dataset(self, dataset_id: str) -> "UsCensusDataset":
        dataset = self.datasets.get(dataset_id)
        if dataset is not None:
            return dataset
        lookup_id = dataset_id.lower()
        for existing_id, existing_dataset in self.datasets.items():
            if existing_id.lower() == lookup_id:
                return existing_dataset
        raise KeyError(dataset_id)


class UsCensusDataset(BaseModel):
    api: UsCensusApi

    c_dataset: list[str]
    c_vintage: int | None = None
    c_geographyLink: str
    c_variablesLink: str
    c_tagsLink: str
    c_examplesLink: str
    c_groupsLink: str
    c_sorts_url: str
    c_documentationLink: str
    c_isAggregate: bool | None = False
    c_isMicrodata: bool | None = False
    c_isTimeseries: bool | None = False
    c_isCube: bool | None = False
    c_isAvailable: bool | None = False
    type: str = Field(alias="@type")
    title: str
    accessLevel: str
    bureauCode: list[str]
    description: str
    distribution: list[dict]
    contactPoint: dict
    identifier: str
    keyword: list[str]
    license: str
    modified: str
    programCode: list[str]
    references: list[str]
    spatial: str | None = None
    temporal: str | None = None
    publisher: dict

    @computed_field
    def name(self) -> str:
        return self.title

    class Geography(BaseModel):
        class Fips(BaseModel):
            name: str
            geoLevelDisplay: str
            referenceDate: str
            requires: list[str] | None = None

        default: list[dict]
        fips: list[Fips]

    class Variable(BaseModel):
        class Values(BaseModel):
            class Range(BaseModel):
                min: str
                max: str
                description: str

            item: dict[str, str] | None = None
            range: list[Range] | None = None

        name: str
        label: str
        concept: str | None = None
        predicateType: str | None = None
        group: str
        limit: int
        is_weight: bool | None = Field(default=None, alias="is-weight")
        suggested_weight: str | None = Field(default=None, alias="suggested-weight")
        values: Values | None = None
        predicateOnly: bool | None = None

        @property
        def codelist(self):
            if self.values:
                return self.values.item

        @property
        def croissant_data_type(self):
            # https://dev.socrata.com/docs/datatypes
            if self.predicateType == "int":
                return mlc.DataType.INTEGER
            if self.predicateType == "string":
                return mlc.DataType.TEXT
            elif self.predicateType == "fips-for":
                return mlc.DataType.TEXT
            elif self.predicateType == "fips-in":
                return mlc.DataType.TEXT
            elif self.predicateType == "ucgid":
                return mlc.DataType.TEXT
            return mlc.DataType.TEXT

    _geography: Geography | None = None
    _variables: dict[str, Variable] | None = None

    @cached_property
    def id(self):
        return self.identifier.split("/")[-1]

    @property
    def stats(self):
        stats = {
            "n_variables": len(self.variables),
            "n_concepts": 0,
            "n_codelists": 0,
            "n_ranges": 0,
            "types": {"none": 0},
            "weights": {},
        }
        for variable in self.variables.values():
            if variable.concept:
                stats["n_concepts"] += 1
            if variable.values:
                if variable.values.item:
                    stats["n_codelists"] += 1
                if variable.values.range:
                    stats["n_ranges"] += 1
            if variable.predicateType:
                if variable.predicateType in stats["types"]:
                    stats["types"][variable.predicateType] += 1
                else:
                    stats["types"][variable.predicateType] = 1
            else:
                stats["types"]["none"] += 1
            if variable.suggested_weight:
                if variable.suggested_weight in stats["weights"]:
                    stats["weights"][variable.suggested_weight] += 1
                else:
                    stats["weights"][variable.suggested_weight] = 1
        return stats

    @property
    def access_url(self):
        return self.distribution[0]["accessURL"]

    @property
    def geography(self):
        if not self._geography:
            # retrieve geography.json file
            # http://api.census.gov/data/2023/acs/acs1/pums/geography.json
            self._variables = {}
            data = self._get_geography()
            self._geography = self.Geography(**data)
        return self._geography

    @property
    def variables(self):
        if not self._variables:
            # retrieve variables.json file
            # http://api.census.gov/data/2023/acs/acs1/pums/variables.json
            self._variables = {}
            data = self._get_variables()
            json_variables = data.get("variables", {})
            for name, variable_data in json_variables.items():
                self._variables[name] = self.Variable(name=name, **variable_data)
        return self._variables

    def _get_geography(self):
        """Retrieve geography.json file from server"""
        data = self.api._session.get(self.c_geographyLink).json()
        return data

    def _get_variables(self):
        """Retrieve variables.json file from server"""
        data = self.api._session.get(self.c_variablesLink).json()
        return data

    def get_croissant(self, include_computed=False) -> mlc.Metadata:
        if include_computed:
            logging.debug("include_computed=True currently returns the same field set as default.")
        context = mlc.Context()
        context.is_live_dataset = True
        # metadata
        publishers = []
        for publisher in self.publisher:
            publishers.append(mlc.Organization(name=publisher))
        metadata = mlc.Metadata(
            ctx=context,
            id=self.id,
            name=self.title,
            description=self.description,
            cite_as=f"{self.title}",
            date_modified=self.modified,
            license=self.license,
            publisher=publishers,
        )
        # distribution
        distribution = []
        content_url = self.access_url
        # content_url += f"?get={','.join(self.variables.keys())}"
        # content_url += "&for=state:10" # delaware FIPS code
        # if not include_computed:
        #    content_url += f'?$select={",".join(selected_variables_names)}'
        fileobject = mlc.FileObject(
            ctx=context,
            id=self.id + ".json",
            name=self.id + ".json",
            content_url=content_url,
            encoding_formats=[mlc.EncodingFormat.JSON],
        )
        distribution.append(fileobject)
        metadata.distribution = distribution
        # fields and record set
        fields = []
        for _name, variable in self.variables.items():
            field = mlc.Field(
                ctx=context,
                id=variable.name,
                name=variable.name,
                description=variable.label,
                source=mlc.Source(file_object=fileobject.id, extract=mlc.Extract(ctx=context, column=variable.name)),
            )
            field.data_types.append(variable.croissant_data_type)
            fields.append(field)
        record_set = mlc.RecordSet(fields=fields)
        record_sets = [record_set]
        metadata.record_sets = record_sets
        return metadata

    def get_dcat_us(self):
        data = self.api._session.get(self.access_url).json()
        return data

    def get_ddi_codebook(self, codebook_version="2.5", include_schema=False) -> str:
        """Generate DDI-Codebook XML for this dataset.

        This generates an XML string so we do not have a dependency on XML packages
        and developers can use the one they like....

        Returns:
            str: The DDI-Codebook XML
        """
        uid = f"uscensus_{self.id}"
        urn = self.identifier
        # codeBook
        xml = (
            f'<codeBook ID="{uid}" ddiCodebookUrn="{urn}" version="{codebook_version}" '
            f'xmlns="ddi:codebook:{codebook_version.replace(".", "_")}"'
        )
        if include_schema:
            xml += (
                ' xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
                'xsi:schemaLocation="ddi:codebook:2_5 '
                'https://ddialliance.org/hubfs/Specification/DDI-Codebook/2.5/XMLSchema/codebook.xsd"'
            )
        xml += ">"
        # docDscr
        xml += "<docDscr>"
        xml += "<citation>"
        xml += "<titlStmt>"
        xml += f"<titl>{escape(self.title)}</titl>"
        xml += f'<IDNo agency="census.gov">{self.id}</IDNo>'
        xml += "</titlStmt>"
        xml += "<prodStmt>"
        prodDate = datetime.now().isoformat()[:-7]
        xml += f'<prodDate date="{prodDate}">{prodDate}</prodDate>'
        xml += f'<software version="{__version__}">Data Artifex - U.S. Census (darfx-uscensus)</software>'
        xml += "</prodStmt>"
        xml += "</citation>"
        xml += "</docDscr>"
        # stdyDscr
        xml += "<stdyDscr>"
        xml += "<citation>"
        xml += "<titlStmt>"
        xml += f"<titl>{escape(self.title)}</titl>"
        xml += f'<IDNo agency="census.gov">{self.id}</IDNo>'
        xml += "</titlStmt>"
        xml += "<prodStmt>"
        # xml += '<software>Socrata</software>'
        xml += "</prodStmt>"
        xml += "</citation>"
        xml += "<stdyInfo>"
        xml += f"<abstract><![CDATA[{escape(self.description)}]]></abstract>"
        xml += "</stdyInfo>"
        xml += "</stdyDscr>"
        # fileDscr
        xml += '<fileDscr ID="F1">'
        xml += "<fileTxt>"
        xml += f"<fileName>{self.id}</fileName>"
        xml += "<dimensns>"
        # xml += f'<caseQnty>{self.get_record_count()}</caseQnty>'
        xml += f"<varQnty>{len(self.variables)}</varQnty>"
        xml += "</dimensns>"
        # xml += '<fileType>socrata</fileType>'
        xml += "</fileTxt>"
        xml += "</fileDscr>"
        # dataDscr
        xml += "<dataDscr>"
        for name, var in self.variables.items():
            if var.predicateOnly:  # skip API predicates
                continue
            xml += f'<var ID="{name}" name="{name}" files="F1"'
            if var.is_weight:
                xml += ' wgt="wgt"'
            if var.suggested_weight:
                xml += f' wgt-var="{var.suggested_weight}"'
                xml += f' weight="{var.suggested_weight}"'
            xml += ">"
            xml += f"<labl>{escape(var.label)}</labl>"
            if var.predicateType == "int":
                type = "numeric"
            else:
                type = "character"
            if var.values and var.values.range:
                for range in var.values.range:
                    xml += "<valrng>"
                    xml += f'<range min="{range.min}" max="{range.max}"/>'
                    if range.description:
                        xml += f'<notes type="darfx" subject="description">{escape(range.description)}</notes>'
                    xml += "</valrng>"
            if var.codelist:
                for value, label in var.codelist.items():
                    xml += "<catgry>"
                    xml += f"<catValu>{escape(value)}</catValu>"
                    xml += f"<labl>{escape(label)}</labl>"
                    xml += "</catgry>"
            xml += (
                f'<varFormat type="{type}" schema="other" formatname="uscensus">{var.predicateType or ""}</varFormat>'
            )
            xml += "</var>"
        xml += "</dataDscr>"
        xml += "</codeBook>"
        return xml


class UsCensusAggregatedDataset(UsCensusDataset):
    pass


class UsCensusTimeSeriesDataset(UsCensusDataset):
    pass


class UsCensusMicrodataDataset(UsCensusDataset):
    pass
