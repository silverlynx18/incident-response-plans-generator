# ARPL Incident Response Plans Generator

ARPL is a Streamlit application for exploring road-incident detours. It downloads an OpenStreetMap driving network for a selected jurisdiction, routes around a closed road segment, ranks candidate detours, and exports reviewed routes.

## Run locally

Use Python 3.10 or newer from this repository's root:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app_v1_5_6.py
```

On Windows, use `.venv\Scripts\python.exe` in place of `.venv/bin/python`.

## Streamlit Community Cloud

Deploy this repository with entry point `app_v1_5_6.py`. Network preparation requires outbound access to OpenStreetMap's Overpass API. Large jurisdictions may exceed free-tier memory or runtime limits; test with a small area first.

## Limitations

Routes are planning aids, not authority-approved traffic-management plans. ARPL has no live traffic, transit, freight-compliance, or capacity model. Saved session files are local and are not suitable for durable multi-user storage.

## Included data

Boundary datasets are 2018 U.S. Census Bureau cartographic boundary files and Bureau of Transportation Statistics Metropolitan Planning Organization boundaries. Their source metadata is included beside each dataset. Census cartographic boundaries are generalized and should not be used for precise legal or area relationships.
