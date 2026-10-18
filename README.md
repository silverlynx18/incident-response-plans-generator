# ARPL - Automated Route Planning & Logistics

A comprehensive traffic detour analysis application with multiple versions, each with its own data directory.

## Repository Structure

```
├── V1/                          # Basic version
│   ├── app.py                   # Main V1 application
│   ├── detour_utils.py          # Core analysis utilities
│   └── data/                    # V1 shapefile data
│       ├── cb_2018_us_state_500k/
│       ├── tiger_2018_counties/
│       ├── BTS_MPO/
│       └── tiger_2018_urban_areas/
│
├── V1.5/                        # Enhanced version
│   ├── app_v1_5.py             # Main V1.5 application
│   ├── detour_utils.py          # Core analysis utilities
│   ├── export_utils.py          # Export functionality
│   ├── requirements.txt         # V1.5 dependencies
│   └── data/                    # V1.5 shapefile data
│       ├── cb_2018_us_state_500k/
│       ├── tiger_2018_counties/
│       ├── BTS_MPO/
│       └── tiger_2018_urban_areas/
│
├── V2/                          # Production version
│   ├── app_v2.py               # Main V2 application
│   ├── detour_utils.py          # Core analysis utilities
│   ├── export_utils.py          # Enhanced export functionality
│   ├── data_manager.py          # Centralized data management
│   ├── session_manager.py       # Session persistence
│   ├── analysis_history.py      # History tracking
│   ├── batch_processor.py       # Batch analysis
│   ├── user_preferences.py      # User settings
│   ├── network_cache.py         # Network caching
│   ├── test_v2_features.py      # Test suite
│   ├── requirements.txt         # V2 dependencies
│   ├── backend/                 # Backend services
│   ├── ui/                      # UI components
│   ├── tests/                   # Test files
│   └── data/                    # V2 shapefile data
│       ├── shapefiles/
│       │   ├── cb_2018_us_state_500k/
│       │   ├── tiger_2018_counties/
│       │   ├── BTS_MPO/
│       │   └── tiger_2018_urban_areas/
│       └── cache/
│
├── database/                    # V2 database files
│   ├── __init__.py
│   ├── schema.py
│   ├── models.py
│   ├── db_manager.py
│   └── arpl_v2.db              # SQLite database
│
├── README.md                    # This file
├── README_V2.md                 # V2-specific documentation
└── requirements.txt             # Main dependencies
```

## Quick Start

### V1 - Basic Version
```bash
cd V1
streamlit run app.py
```

### V1.5 - Enhanced Version
```bash
cd V1.5
pip install -r requirements.txt
streamlit run app_v1_5.py
```

### V2 - Production Version
```bash
cd V2
pip install -r requirements.txt
streamlit run app_v2.py
```

## Features by Version

### V1 Features
- Basic detour analysis
- Local shapefile support
- Simple map visualization
- Basic route results

### V1.5 Features
- All V1 features
- Enhanced export functionality (PDF, GeoJSON, KML, Shapefile, Excel, CSV)
- Improved UI and visualization
- Better error handling

### V2 Features
- All V1.5 features
- Database persistence (SQLite)
- Session save/load functionality
- Batch processing for multiple incidents
- Network caching for performance
- User preferences system
- Analysis history tracking
- Enhanced export with session metadata
- Comprehensive test suite

## Data Structure

Each version has its own data directory:
- **V1/data/**: Contains TIGER 2018 shapefile data for V1
- **V1.5/data/**: Contains TIGER 2018 shapefile data for V1.5
- **V2/data/**: Contains TIGER 2018 shapefile data and cache for V2

Each version is completely independent and can be run without affecting the others.

## Dependencies

### V1
- streamlit
- pandas
- geopandas
- folium
- streamlit-folium
- osmnx
- networkx
- shapely

### V1.5
- All V1 dependencies
- reportlab (PDF reports)
- openpyxl (Excel export)
- fiona (Shapefile export)
- pyproj (Coordinate transformations)

### V2
- All V1.5 dependencies
- sqlalchemy (Database ORM)
- alembic (Database migrations)

## Development

### Running Tests (V2 only)
```bash
cd V2
python test_v2_features.py
```

### Database Management (V2 only)
The V2 database is automatically created on first run. Database files are stored in the `database/` directory.

## Migration Path

1. **V1 → V1.5**: Direct upgrade, no data migration needed
2. **V1.5 → V2**: Database auto-creates, preferences can be imported
3. **V2**: Full backward compatibility with V1.5

## Support

- V1: Basic support for core functionality
- V1.5: Enhanced support with export features
- V2: Full production support with database and session management

## License

See individual version documentation for licensing information.
