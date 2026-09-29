"""Pull the live field list for the NFIP datasets straight from FEMA's metadata API.

Run this first, and any time the pipeline complains about a missing column.
It writes docs/schema_<dataset>.json so the build step can validate against
the real schema instead of a hard-coded guess.
"""
import json
import pathlib
import urllib.parse
import urllib.request

API = "https://www.fema.gov/api/open/v1"
DOCS = pathlib.Path(__file__).resolve().parents[1] / "docs"

DATASETS = [("NfipClaims", 3), ("NfipPolicies", 3), ("NfipMultipleLossProperties", 1)]


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "nfip-analytics/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def fetch_fields(dataset: str, version: int) -> list[dict]:
    flt = f"openFemaDataSet eq '{dataset}' and datasetVersion eq {version}"
    qs = urllib.parse.urlencode(
        {"$filter": flt, "$top": 500, "$select": "name,title,type,description"}
    )
    return get(f"{API}/OpenFemaDataSetFields?{qs}")["OpenFemaDataSetFields"]


def fetch_dataset_meta(dataset: str) -> dict:
    qs = urllib.parse.urlencode({"$filter": f"name eq '{dataset}'"})
    rows = get(f"{API}/OpenFemaDataSets?{qs}")["OpenFemaDataSets"]
    return max(rows, key=lambda r: r.get("version", 0)) if rows else {}


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    for dataset, version in DATASETS:
        fields = fetch_fields(dataset, version)
        meta = fetch_dataset_meta(dataset)
        out = {
            "dataset": dataset,
            "version": version,
            "recordCount": meta.get("recordCount"),
            "lastRefresh": meta.get("lastRefresh"),
            "distribution": meta.get("distribution", []),
            "fields": fields,
        }
        path = DOCS / f"schema_{dataset}.json"
        path.write_text(json.dumps(out, indent=2))
        print(f"{dataset} v{version}: {len(fields)} fields, "
              f"{meta.get('recordCount'):,} records -> {path.name}")


if __name__ == "__main__":
    main()
