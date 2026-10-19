"""
Batch processing module for ARPL V2.
Handles analysis of multiple incidents in batch operations.
"""

import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Callable
import networkx as nx

from database import DatabaseManager
from analysis_history import AnalysisHistory

class BatchProcessor:
    """Handles batch processing of multiple incident analyses."""

    def __init__(self, db_manager: DatabaseManager):
        """Initialize batch processor with database connection."""
        self.db_manager = db_manager
        self.history = AnalysisHistory(db_manager)

    def run_batch_analysis(
        self,
        graph: nx.Graph,
        incident_edges: List[Tuple[int, int]],
        analysis_params: Dict[str, Any],
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Run batch analysis on multiple incident edges.

        Args:
            graph: NetworkX graph to analyze
            incident_edges: List of (u, v) edge tuples to analyze
            analysis_params: Analysis parameters dictionary
            progress_callback: Optional callback for progress updates (current, total)

        Returns:
            Dictionary containing batch results and statistics
        """
        start_time = time.time()
        results = {}
        total_edges = len(incident_edges)

        for i, incident_edge in enumerate(incident_edges):
            try:
                # Update progress
                if progress_callback:
                    progress_callback(i + 1, total_edges)

                # Analyze single incident
                result = self.analyze_incident(graph, incident_edge, analysis_params)
                results[incident_edge] = result

            except Exception as e:
                # Record error but continue with other incidents
                results[incident_edge] = {
                    'error': str(e),
                    'detour_results': {},
                    'valid_detours': 0,
                    'success_rate': 0.0,
                    'processing_time': 0.0
                }

        # Calculate batch statistics
        total_time = time.time() - start_time
        batch_stats = self._calculate_batch_stats(results)

        # Record batch analysis in history
        self.history.record_analysis(
            jurisdiction=analysis_params.get('jurisdiction', 'Batch Analysis'),
            total_routes=batch_stats['total_routes'],
            valid_routes=batch_stats['valid_routes'],
            parameters={
                **analysis_params,
                'batch_size': total_edges,
                'incident_edges': [f"{u}-{v}" for u, v in incident_edges]
            },
            processing_time_seconds=total_time
        )

        return {
            'results': results,
            'statistics': batch_stats,
            'total_processing_time': total_time,
            'incident_count': total_edges,
            'timestamp': datetime.utcnow().isoformat()
        }

    def analyze_incident(
        self,
        graph: nx.Graph,
        incident_edge: Tuple[int, int],
        analysis_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze a single incident edge.

        Args:
            graph: NetworkX graph
            incident_edge: (u, v) edge tuple
            analysis_params: Analysis parameters

        Returns:
            Analysis result dictionary
        """
        start_time = time.time()

        try:
            # Import detour_utils here to avoid circular imports
            import detour_utils as du

            u, v = incident_edge

            # Extract analysis parameters
            turn_nodes = analysis_params.get('turn_nodes', 5)
            sector_angle = analysis_params.get('sector_angle', 180)
            max_detour_length = analysis_params.get('max_detour_length', 2.0)

            # Find detour routes
            detour_results = du.find_detour_routes(
                graph, u, v,
                turn_nodes=turn_nodes,
                sector_angle=sector_angle,
                max_detour_length=max_detour_length
            )

            # Count valid detours
            valid_detours = sum(1 for result in detour_results.values() if result[0])
            total_routes = len(detour_results)
            success_rate = (valid_detours / total_routes * 100) if total_routes > 0 else 0.0

            processing_time = time.time() - start_time

            return {
                'detour_results': detour_results,
                'valid_detours': valid_detours,
                'total_routes': total_routes,
                'success_rate': success_rate,
                'processing_time': processing_time,
                'incident_edge': incident_edge
            }

        except Exception as e:
            processing_time = time.time() - start_time
            return {
                'error': str(e),
                'detour_results': {},
                'valid_detours': 0,
                'total_routes': 0,
                'success_rate': 0.0,
                'processing_time': processing_time,
                'incident_edge': incident_edge
            }

    def _calculate_batch_stats(self, results: Dict[Tuple[int, int], Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate statistics for batch results."""
        total_routes = 0
        valid_routes = 0
        total_processing_time = 0.0
        successful_analyses = 0
        failed_analyses = 0

        for result in results.values():
            if 'error' in result:
                failed_analyses += 1
            else:
                successful_analyses += 1
                total_routes += result.get('total_routes', 0)
                valid_routes += result.get('valid_detours', 0)
                total_processing_time += result.get('processing_time', 0.0)

        overall_success_rate = (valid_routes / total_routes * 100) if total_routes > 0 else 0.0
        analysis_success_rate = (successful_analyses / len(results) * 100) if results else 0.0

        return {
            'total_routes': total_routes,
            'valid_routes': valid_routes,
            'overall_success_rate': round(overall_success_rate, 1),
            'analysis_success_rate': round(analysis_success_rate, 1),
            'successful_analyses': successful_analyses,
            'failed_analyses': failed_analyses,
            'total_processing_time': round(total_processing_time, 2),
            'average_processing_time': round(total_processing_time / len(results), 2) if results else 0.0
        }

    def get_batch_summary(self, batch_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate a summary of batch results for display.

        Args:
            batch_results: Results from run_batch_analysis

        Returns:
            Summary dictionary for UI display
        """
        results = batch_results.get('results', {})
        stats = batch_results.get('statistics', {})

        # Create summary table data
        summary_data = []
        for incident_edge, result in results.items():
            if 'error' in result:
                summary_data.append({
                    'Incident Edge': f"{incident_edge[0]}-{incident_edge[1]}",
                    'Status': 'Failed',
                    'Error': result['error'][:50] + '...' if len(result['error']) > 50 else result['error'],
                    'Total Routes': 0,
                    'Valid Routes': 0,
                    'Success Rate': '0.0%',
                    'Processing Time': f"{result.get('processing_time', 0):.2f}s"
                })
            else:
                summary_data.append({
                    'Incident Edge': f"{incident_edge[0]}-{incident_edge[1]}",
                    'Status': 'Success',
                    'Error': '',
                    'Total Routes': result.get('total_routes', 0),
                    'Valid Routes': result.get('valid_detours', 0),
                    'Success Rate': f"{result.get('success_rate', 0):.1f}%",
                    'Processing Time': f"{result.get('processing_time', 0):.2f}s"
                })

        return {
            'summary_table': summary_data,
            'overall_stats': stats,
            'total_incidents': len(results),
            'batch_timestamp': batch_results.get('timestamp'),
            'total_batch_time': batch_results.get('total_processing_time', 0)
        }

    def export_batch_results(
        self,
        batch_results: Dict[str, Any],
        format: str = 'json'
    ) -> str:
        """
        Export batch results in specified format.

        Args:
            batch_results: Results from run_batch_analysis
            format: Export format ('json', 'csv')

        Returns:
            Exported data as string
        """
        if format.lower() == 'json':
            import json
            return json.dumps(batch_results, indent=2, default=str)

        elif format.lower() == 'csv':
            import csv
            import io

            summary = self.get_batch_summary(batch_results)
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=[
                'Incident Edge', 'Status', 'Error', 'Total Routes',
                'Valid Routes', 'Success Rate', 'Processing Time'
            ])

            writer.writeheader()
            writer.writerows(summary['summary_table'])

            return output.getvalue()

        else:
            raise ValueError(f"Unsupported export format: {format}")

    def validate_incident_edges(
        self,
        graph: nx.Graph,
        incident_edges: List[Tuple[int, int]]
    ) -> Dict[str, List[Tuple[int, int]]]:
        """
        Validate incident edges against the graph.

        Args:
            graph: NetworkX graph
            incident_edges: List of (u, v) edge tuples

        Returns:
            Dictionary with 'valid' and 'invalid' edge lists
        """
        valid_edges = []
        invalid_edges = []

        for edge in incident_edges:
            u, v = edge
            if graph.has_edge(u, v):
                valid_edges.append(edge)
            else:
                invalid_edges.append(edge)

        return {
            'valid': valid_edges,
            'invalid': invalid_edges
        }
