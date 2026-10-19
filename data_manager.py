"""
Data manager module for ARPL V2.
Centralized data operations and management for TIGER data and custom data sources.
"""

import os
import requests
import geopandas as gpd
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
import tempfile
import zipfile
from pathlib import Path

class DataManager:
    """Centralized data management for geospatial datasets."""

    def __init__(self, data_dir: str = "data"):
        """Initialize data manager with data directory."""
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)

        # TIGER data configuration
        self.tiger_config = {
            "2018": {
                "base_url": "https://www2.census.gov/geo/tiger/TIGER2018",
                "datasets": {
                    "states": "STATE/tl_2018_us_state.shp",
                    "counties": "COUNTY/tl_2018_us_county.shp",
                    "urban_areas": "UAC/tl_2018_us_uac10.shp",
                    "mpos": "MPO/tl_2018_us_mpo.shp"
                }
            },
            "2024": {
                "base_url": "https://www2.census.gov/geo/tiger/TIGER2024",
                "datasets": {
                    "states": "STATE/tl_2024_us_state.shp",
                    "counties": "COUNTY/tl_2024_us_county.shp",
                    "urban_areas": "UAC/tl_2024_us_uac20.shp"
                }
            }
        }

        # Local shapefile paths (for existing V1.5 data)
        self.local_paths = {
            "states": "cb_2018_us_state_500k",
            "counties": "tiger_2018_counties",
            "mpos": "BTS_MPO",
            "ua": "tiger_2018_urban_areas"
        }

    def load_tiger_data(self, dataset: str, year: str = "2018") -> Optional[gpd.GeoDataFrame]:
        """
        Load TIGER data from local files or download if needed.

        Args:
            dataset: Dataset name (states, counties, urban_areas, mpos)
            year: Data year (2018, 2024)

        Returns:
            GeoDataFrame or None if failed
        """
        # First try local files
        local_gdf = self._load_local_shapefile(dataset)
        if local_gdf is not None:
            return local_gdf

        # If not found locally, try to download
        return self.download_tiger_data(dataset, year)

    def _load_local_shapefile(self, dataset: str) -> Optional[gpd.GeoDataFrame]:
        """Load shapefile from local directory."""
        if dataset not in self.local_paths:
            return None

        path = self.local_paths[dataset]
        if not os.path.isdir(path):
            return None

        try:
            shp_files = [f for f in os.listdir(path) if f.endswith('.shp')]
            if not shp_files:
                return None

            gdf = gpd.read_file(os.path.join(path, shp_files[0]))
            if gdf.crs.to_epsg() != 4326:
                gdf = gdf.to_crs(epsg=4326)

            return gdf

        except Exception as e:
            print(f"Error loading local shapefile {dataset}: {e}")
            return None

    def download_tiger_data(
        self,
        dataset: str,
        year: str = "2018",
        progress_callback: Optional[callable] = None
    ) -> Optional[gpd.GeoDataFrame]:
        """
        Download TIGER data from Census Bureau.

        Args:
            dataset: Dataset name
            year: Data year
            progress_callback: Optional progress callback

        Returns:
            GeoDataFrame or None if failed
        """
        if year not in self.tiger_config:
            print(f"Unsupported year: {year}")
            return None

        if dataset not in self.tiger_config[year]["datasets"]:
            print(f"Unsupported dataset: {dataset}")
            return None

        try:
            config = self.tiger_config[year]
            url = f"{config['base_url']}/{config['datasets'][dataset]}"

            if progress_callback:
                progress_callback(f"Downloading {dataset} data from {year}...")

            # Download the shapefile
            response = requests.get(url, stream=True)
            response.raise_for_status()

            # Save to temporary file
            with tempfile.NamedTemporaryFile(suffix='.shp', delete=False) as tmp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)
                tmp_path = tmp_file.name

            # Load the shapefile
            gdf = gpd.read_file(tmp_path)

            # Convert to WGS84 if needed
            if gdf.crs.to_epsg() != 4326:
                gdf = gdf.to_crs(epsg=4326)

            # Clean up temp file
            os.unlink(tmp_path)

            if progress_callback:
                progress_callback(f"Successfully loaded {dataset} data")

            return gdf

        except Exception as e:
            print(f"Error downloading TIGER data {dataset} {year}: {e}")
            return None

    def load_custom_data(self, url: str, layer: Optional[int] = None) -> Optional[gpd.GeoDataFrame]:
        """
        Load custom data from URL (ArcGIS REST service or other).

        Args:
            url: Data URL
            layer: Layer number for ArcGIS services

        Returns:
            GeoDataFrame or None if failed
        """
        try:
            if "arcgis.com" in url or "geoserver" in url.lower():
                return self._load_arcgis_data(url, layer)
            else:
                # Try direct file download
                return self._load_direct_file(url)

        except Exception as e:
            print(f"Error loading custom data from {url}: {e}")
            return None

    def _load_arcgis_data(self, url: str, layer: Optional[int] = None) -> Optional[gpd.GeoDataFrame]:
        """Load data from ArcGIS REST service."""
        try:
            # Construct query URL
            if layer is not None:
                query_url = f"{url}/{layer}/query"
            else:
                query_url = f"{url}/query"

            params = {
                'where': '1=1',
                'outFields': '*',
                'f': 'geojson',
                'outSR': '4326'
            }

            response = requests.get(query_url, params=params)
            response.raise_for_status()

            # Load as GeoDataFrame
            gdf = gpd.read_file(response.text, driver='GeoJSON')

            return gdf

        except Exception as e:
            print(f"Error loading ArcGIS data: {e}")
            return None

    def _load_direct_file(self, url: str) -> Optional[gpd.GeoDataFrame]:
        """Load data from direct file URL."""
        try:
            # Download file
            response = requests.get(url)
            response.raise_for_status()

            # Determine file type and load
            if url.endswith('.geojson') or url.endswith('.json'):
                gdf = gpd.read_file(response.text, driver='GeoJSON')
            elif url.endswith('.shp'):
                # Save to temp file and load
                with tempfile.NamedTemporaryFile(suffix='.shp', delete=False) as tmp_file:
                    tmp_file.write(response.content)
                    tmp_path = tmp_file.name

                gdf = gpd.read_file(tmp_path)
                os.unlink(tmp_path)
            else:
                # Try to load as GeoJSON
                gdf = gpd.read_file(response.text, driver='GeoJSON')

            return gdf

        except Exception as e:
            print(f"Error loading direct file: {e}")
            return None

    def validate_data_quality(self, gdf: gpd.GeoDataFrame) -> Dict[str, Any]:
        """
        Validate data quality of a GeoDataFrame.

        Args:
            gdf: GeoDataFrame to validate

        Returns:
            Dictionary with quality metrics
        """
        if gdf is None or gdf.empty:
            return {"status": "invalid", "reason": "Empty or None data"}

        quality_metrics = {
            "status": "valid",
            "total_features": len(gdf),
            "geometry_types": gdf.geometry.geom_type.value_counts().to_dict(),
            "crs": str(gdf.crs) if gdf.crs else "No CRS",
            "bounds": gdf.total_bounds.tolist() if not gdf.empty else None,
            "columns": list(gdf.columns),
            "null_geometries": gdf.geometry.isna().sum(),
            "invalid_geometries": (~gdf.geometry.is_valid).sum() if hasattr(gdf.geometry, 'is_valid') else 0
        }

        # Check for common issues
        issues = []
        if quality_metrics["null_geometries"] > 0:
            issues.append(f"{quality_metrics['null_geometries']} null geometries")

        if quality_metrics["invalid_geometries"] > 0:
            issues.append(f"{quality_metrics['invalid_geometries']} invalid geometries")

        if not gdf.crs:
            issues.append("No coordinate reference system")

        if len(gdf) == 0:
            issues.append("No features in dataset")

        quality_metrics["issues"] = issues
        if issues:
            quality_metrics["status"] = "warning"

        return quality_metrics

    def get_data_statistics(self) -> Dict[str, Any]:
        """
        Get statistics on available data.

        Returns:
            Dictionary with data statistics
        """
        stats = {
            "local_data": {},
            "available_datasets": list(self.tiger_config["2018"]["datasets"].keys()),
            "supported_years": list(self.tiger_config.keys())
        }

        # Check local data availability
        for dataset, path in self.local_paths.items():
            if os.path.isdir(path):
                try:
                    gdf = self._load_local_shapefile(dataset)
                    if gdf is not None:
                        stats["local_data"][dataset] = {
                            "available": True,
                            "features": len(gdf),
                            "path": path,
                            "quality": self.validate_data_quality(gdf)
                        }
                    else:
                        stats["local_data"][dataset] = {"available": False, "path": path}
                except Exception as e:
                    stats["local_data"][dataset] = {
                        "available": False,
                        "path": path,
                        "error": str(e)
                    }
            else:
                stats["local_data"][dataset] = {"available": False, "path": path}

        return stats

    def load_all_shapefiles(self) -> Dict[str, Optional[gpd.GeoDataFrame]]:
        """
        Load all available shapefiles.

        Returns:
            Dictionary of dataset name to GeoDataFrame
        """
        gdfs = {}

        for dataset in ["states", "counties", "mpos", "ua"]:
            gdfs[dataset] = self.load_tiger_data(dataset, "2018")

        return gdfs

    def export_data_summary(self, gdf: gpd.GeoDataFrame, format: str = "json") -> str:
        """
        Export data summary in specified format.

        Args:
            gdf: GeoDataFrame to summarize
            format: Export format (json, csv)

        Returns:
            Summary as string
        """
        if gdf is None or gdf.empty:
            return "No data to summarize"

        summary = {
            "total_features": len(gdf),
            "geometry_types": gdf.geometry.geom_type.value_counts().to_dict(),
            "crs": str(gdf.crs) if gdf.crs else "No CRS",
            "bounds": {
                "minx": float(gdf.total_bounds[0]),
                "miny": float(gdf.total_bounds[1]),
                "maxx": float(gdf.total_bounds[2]),
                "maxy": float(gdf.total_bounds[3])
            },
            "columns": list(gdf.columns),
            "sample_data": gdf.head(3).to_dict('records') if len(gdf) > 0 else []
        }

        if format.lower() == "json":
            import json
            return json.dumps(summary, indent=2, default=str)
        elif format.lower() == "csv":
            # Convert to DataFrame and export
            df = pd.DataFrame([summary])
            return df.to_csv(index=False)
        else:
            return str(summary)

    def get_jurisdiction_info(self, gdf: gpd.GeoDataFrame, name_column: str = "NAME") -> List[Dict[str, Any]]:
        """
        Get information about jurisdictions in the dataset.

        Args:
            gdf: GeoDataFrame
            name_column: Column containing jurisdiction names

        Returns:
            List of jurisdiction information
        """
        if gdf is None or gdf.empty or name_column not in gdf.columns:
            return []

        jurisdictions = []
        for idx, row in gdf.iterrows():
            jurisdiction_info = {
                "index": idx,
                "name": row.get(name_column, f"Feature {idx}"),
                "geometry_type": row.geometry.geom_type if hasattr(row, 'geometry') else "Unknown",
                "area": row.geometry.area if hasattr(row, 'geometry') else 0
            }

            # Add other relevant columns
            for col in gdf.columns:
                if col not in ['geometry', name_column]:
                    jurisdiction_info[col] = row[col]

            jurisdictions.append(jurisdiction_info)

        return jurisdictions
