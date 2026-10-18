# ARPL V1.6.1 Deployment Package

## Package Contents

This archive contains all files necessary to run the ARPL (Alternative Route Planning Library) Traffic Detour Finder application version 1.6.1.

### Core Application Files
- `app.py` - Main Streamlit application
- `detour_utils.py` - Core detour analysis and visualization utilities
- `export_utils_v1_5_6.py` - Export functions (PDF, GeoJSON, KML, Shapefile, Excel, CSV)
- `osm_network_loader.py` - OSM network data loading utilities
- `trafficsignal.svg` - Traffic signal icon for map visualization

### Configuration Files
- `requirements.txt` - Python package dependencies
- `packages.txt` - System-level dependencies (for Linux/Ubuntu)
- `.streamlit/config.toml` - Streamlit configuration

### Data Files
- `data/` - Contains all shapefiles and OSM network data:
  - `BTS_MPO/` - Metropolitan Planning Organization boundaries
  - `cb_2018_us_state_500k/` - US state boundaries
  - `tiger_2018_counties/` - US county boundaries
  - `tiger_2018_urban_areas/` - US urban area boundaries
  - `osm_networks/` - Pre-processed OSM road network data

### Deployment Scripts
- `run.sh` - Linux/macOS deployment script
- `run.bat` - Windows deployment script

## Installation Instructions

### Prerequisites

1. **Python 3.8+** installed on your system
2. **System dependencies** (for Linux/Ubuntu):
   ```bash
   sudo apt-get update
   sudo apt-get install -y $(cat packages.txt)
   ```

### Setup Steps

1. **Extract the archive:**
   ```bash
   tar -xzf ARPL_V1_6_1_Portable.tar.gz
   cd ARPL_V1_6_1_Portable
   ```

2. **Create a virtual environment (recommended):**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application:**
   ```bash
   # Linux/macOS
   ./run.sh
   
   # Windows
   run.bat
   
   # Or directly with Streamlit
   streamlit run app.py
   ```

5. **Access the application:**
   - Open your browser to `http://localhost:8501`
   - The application will start with the setup wizard

## Key Features in V1.6.1

- **Buffer Search**: Enhanced buffer search with proper CRS handling and distance filtering
- **Traffic Signal Support**: Automatic detection of traffic signal datasets with major/minor road extraction
- **Complete PDF Reports**: All route segments and buffer search results included (paginated if needed)
- **Improved Visualization**: Traffic signal icons on maps, proper legend, directional arrows
- **Export Formats**: PDF, GeoJSON, KML, KMZ, Shapefile, Excel, CSV
- **Jurisdiction Filtering**: Proper state and jurisdiction selection with custom jurisdiction support

## Troubleshooting

### Port Already in Use
If port 8501 is already in use, modify `.streamlit/config.toml` to change the port:
```toml
[server]
port = 8502
```

### Missing System Dependencies
On Linux/Ubuntu, ensure all packages from `packages.txt` are installed. On macOS, use Homebrew:
```bash
brew install gdal proj geos
```

### OSM Network Data
The application includes pre-processed OSM network data in `data/osm_networks/`. If you need to regenerate this data, the application will do so automatically when you select a jurisdiction.

## Support

For detailed user documentation, see `README.md` in this package.

## Version Information

- **Version**: 1.6.1
- **Release Date**: November 2024
- **Python**: 3.8+
- **Streamlit**: 1.28.0+

