# ARPL V1.6.2 Portable - Traffic Detour Analysis Application

## Quick Start

### Linux/macOS:
```bash
./run.sh
```

### Windows:
```cmd
run.bat
```

## What's Included

- **app.py** - Main application (V1.6.2)
- **detour_utils.py** - Core analysis algorithms
- **export_utils_v1_5_6.py** - Export functionality (PDF, GeoJSON, KML, KMZ, Shapefile, Excel, CSV)
- **osm_network_loader.py** - Network data loading
- **requirements.txt** - Python dependencies
- **packages.txt** - System dependencies (for Linux)
- **data/** - Shapefiles and network data
- **.streamlit/config.toml** - Streamlit configuration

## Features

- Enhanced buffer search with meter-based calculations
- Improved visualization (blue detour routes, red incident links)
- Fixed jurisdiction selection (correctly filters by state)
- Complete export functionality with maps
- Paginated route segments and buffer search results
- Dynamic major/minor road detection
- Traffic signal icons on maps

## Requirements

- Python 3.8 or higher
- pip
- Internet connection (for OSM network downloads)

## System Dependencies (Linux)

If deploying on Linux, install system dependencies:
```bash
sudo apt-get update
sudo apt-get install -y $(cat packages.txt)
```

## Version

**V1.6.2** - Local Development Version
- All V1.6.1 improvements included
- Enhanced map generation in PDF exports
- Fixed jurisdiction selection cache issue

