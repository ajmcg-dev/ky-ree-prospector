"""The shape of data we want Claude to pull out of each report.

These Pydantic classes do double duty:
1. They tell Claude exactly what fields to fill in (sent as a JSON schema).
2. They validate the answer: if Claude returns something malformed, Python
   raises an error instead of silently saving bad data.
"""

from typing import Literal

from pydantic import BaseModel, Field

SampleType = Literal[
    "water_dissolved",     # filtered water sample
    "water_total",         # unfiltered water sample
    "precipitate",         # orange iron/aluminum "yellow boy" sludge, treatment solids
    "sediment",            # stream-bed sediment
    "leachate",            # lab or refuse-pile leachate
    "coal_or_rock",        # coal, clay, shale, refuse
    "other",
]

SiteContext = Literal[
    "untreated_discharge",  # raw mine drainage at the source
    "treated_effluent",     # water leaving a treatment system
    "treatment_solids",     # sludge collected from a treatment system
    "receiving_stream",     # a creek/river downstream of mining
    "refuse_pile",
    "laboratory",
    "unknown",
]

StatKind = Literal["single", "mean", "median", "min", "max"]


class ElementValue(BaseModel):
    element: str = Field(description="Element symbol, e.g. 'Nd', 'Y', 'Sc', or 'TREE' / 'TREY' for a reported total.")
    value: float = Field(description="Number exactly as printed in the report. Do not convert units.")
    units: str = Field(description="Units exactly as printed, e.g. 'ug/L', 'mg/L', 'mg/kg', 'ppm'.")
    stat: StatKind = Field(description="'single' for one sample's value; otherwise which summary statistic it is.")


class Site(BaseModel):
    site_name: str = Field(description="Site or sample name as written in the report.")
    state: str | None = Field(description="Two-letter US state code (e.g. 'KY', 'PA', 'WV'), or null if not stated.")
    location_description: str | None = Field(description="County, watershed, or other location text, if given.")
    latitude: float | None = Field(description="Decimal degrees if printed in the report, else null. Never guess.")
    longitude: float | None = Field(description="Decimal degrees if printed in the report, else null. Never guess.")
    coal_basin_or_seam: str | None = Field(description="Coal basin, field, or seam name if stated (e.g. 'Central Appalachian', 'Fire Clay').")
    sample_type: SampleType
    site_context: SiteContext
    ph: float | None = Field(description="pH of the water at this site, if reported.")
    sulfate_mg_l: float | None = None
    aluminum_mg_l: float | None = None
    iron_mg_l: float | None = None
    manganese_mg_l: float | None = None
    ree_values: list[ElementValue] = Field(description="Every rare earth value reported for this site/sample.")
    page: int | None = Field(description="PDF page number where these values appear.")
    evidence: str = Field(description="Short identifier for where the numbers came from, e.g. 'Table 3, row LR-2'.")


class PaperExtraction(BaseModel):
    paper_title: str
    study_region: str = Field(description="Where the samples came from, in a few words.")
    sites: list[Site]
    notes: str = Field(description="Anything a data scientist should know: units caveats, missing tables, supplementary files not included.")
