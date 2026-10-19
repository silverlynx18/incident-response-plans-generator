"""
Analysis history tracking module for ARPL V2.
Records and manages analysis history and statistics.
"""

import csv
import io
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from database import DatabaseManager, AnalysisHistory as AnalysisHistoryModel

class AnalysisHistory:
    """Manages analysis history tracking and statistics."""

    def __init__(self, db_manager: DatabaseManager):
        """Initialize analysis history manager."""
        self.db_manager = db_manager

    def record_analysis(
        self,
        jurisdiction: str,
        total_routes: int,
        valid_routes: int,
        parameters: Dict[str, Any],
        processing_time_seconds: float = 0.0
    ) -> Optional[int]:
        """
        Record an analysis in the history.

        Args:
            jurisdiction: Name of the jurisdiction analyzed
            total_routes: Total number of routes analyzed
            valid_routes: Number of valid routes found
            parameters: Analysis parameters used
            processing_time_seconds: Time taken for analysis

        Returns:
            History record ID if successful, None otherwise
        """
        try:
            with self.db_manager.get_session() as db:
                success_rate = (valid_routes / total_routes * 100) if total_routes > 0 else 0.0

                history_record = AnalysisHistoryModel(
                    jurisdiction=jurisdiction,
                    total_routes=total_routes,
                    valid_routes=valid_routes,
                    success_rate=success_rate,
                    parameters=parameters,
                    processing_time_seconds=processing_time_seconds
                )

                db.add(history_record)
                db.commit()
                return history_record.id

        except Exception as e:
            print(f"Error recording analysis: {e}")
            return None

    def get_history(self, limit: int = 50, jurisdiction: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get analysis history records.

        Args:
            limit: Maximum number of records to return
            jurisdiction: Filter by jurisdiction (optional)

        Returns:
            List of history records
        """
        try:
            with self.db_manager.get_session() as db:
                query = db.query(AnalysisHistoryModel)

                if jurisdiction:
                    query = query.filter(AnalysisHistoryModel.jurisdiction == jurisdiction)

                records = query.order_by(desc(AnalysisHistoryModel.timestamp)).limit(limit).all()

                return [
                    {
                        "id": record.id,
                        "jurisdiction": record.jurisdiction,
                        "timestamp": record.timestamp.isoformat() if record.timestamp else None,
                        "total_routes": record.total_routes,
                        "valid_routes": record.valid_routes,
                        "success_rate": round(record.success_rate, 1),
                        "processing_time": round(record.processing_time_seconds, 2),
                        "parameters": record.parameters
                    }
                    for record in records
                ]

        except Exception as e:
            print(f"Error getting history: {e}")
            return []

    def get_statistics(self, days: int = 30) -> Dict[str, Any]:
        """
        Get analysis statistics for the specified period.

        Args:
            days: Number of days to look back

        Returns:
            Statistics dictionary
        """
        try:
            with self.db_manager.get_session() as db:
                cutoff_date = datetime.utcnow() - timedelta(days=days)

                # Basic counts
                total_analyses = db.query(AnalysisHistoryModel).filter(
                    AnalysisHistoryModel.timestamp >= cutoff_date
                ).count()

                # Success rate statistics
                success_stats = db.query(
                    func.avg(AnalysisHistoryModel.success_rate).label('avg_success'),
                    func.min(AnalysisHistoryModel.success_rate).label('min_success'),
                    func.max(AnalysisHistoryModel.success_rate).label('max_success')
                ).filter(
                    AnalysisHistoryModel.timestamp >= cutoff_date
                ).first()

                # Route statistics
                route_stats = db.query(
                    func.sum(AnalysisHistoryModel.total_routes).label('total_routes'),
                    func.sum(AnalysisHistoryModel.valid_routes).label('valid_routes'),
                    func.avg(AnalysisHistoryModel.processing_time_seconds).label('avg_processing_time')
                ).filter(
                    AnalysisHistoryModel.timestamp >= cutoff_date
                ).first()

                # Jurisdiction breakdown
                jurisdiction_stats = db.query(
                    AnalysisHistoryModel.jurisdiction,
                    func.count(AnalysisHistoryModel.id).label('count'),
                    func.avg(AnalysisHistoryModel.success_rate).label('avg_success')
                ).filter(
                    AnalysisHistoryModel.timestamp >= cutoff_date
                ).group_by(AnalysisHistoryModel.jurisdiction).all()

                return {
                    "period_days": days,
                    "total_analyses": total_analyses,
                    "success_rate": {
                        "average": round(success_stats.avg_success or 0, 1),
                        "minimum": round(success_stats.min_success or 0, 1),
                        "maximum": round(success_stats.max_success or 0, 1)
                    },
                    "routes": {
                        "total_analyzed": route_stats.total_routes or 0,
                        "total_valid": route_stats.valid_routes or 0,
                        "average_processing_time": round(route_stats.avg_processing_time or 0, 2)
                    },
                    "jurisdictions": [
                        {
                            "name": stat.jurisdiction,
                            "analyses": stat.count,
                            "avg_success_rate": round(stat.avg_success or 0, 1)
                        }
                        for stat in jurisdiction_stats
                    ]
                }

        except Exception as e:
            print(f"Error getting statistics: {e}")
            return {}

    def export_to_csv(self, limit: int = 1000) -> str:
        """
        Export analysis history to CSV format.

        Args:
            limit: Maximum number of records to export

        Returns:
            CSV content as string
        """
        try:
            history = self.get_history(limit=limit)

            if not history:
                return "No analysis history found."

            output = io.StringIO()
            output.write("# Analysis Metadata\n")
            output.write(f"# Export Date: {datetime.utcnow().isoformat()}\n")
            output.write(f"# Record Count: {len(history)}\n\n")

            writer = csv.DictWriter(output, fieldnames=[
                'id', 'jurisdiction', 'timestamp', 'total_routes',
                'valid_routes', 'success_rate', 'processing_time', 'parameters'
            ])

            writer.writeheader()
            for record in history:
                # Convert parameters dict to string for CSV
                record_copy = record.copy()
                record_copy['parameters'] = str(record['parameters'])
                writer.writerow(record_copy)

            return output.getvalue()


        except Exception as e:
            print(f"Error exporting to CSV: {e}")
            return f"Export failed: {e}"

    def get_recent_analyses(self, hours: int = 24) -> List[Dict[str, Any]]:
        """
        Get analyses from the last N hours.

        Args:
            hours: Number of hours to look back

        Returns:
            List of recent analysis records
        """
        try:
            with self.db_manager.get_session() as db:
                cutoff_time = datetime.utcnow() - timedelta(hours=hours)

                records = db.query(AnalysisHistoryModel).filter(
                    AnalysisHistoryModel.timestamp >= cutoff_time
                ).order_by(desc(AnalysisHistoryModel.timestamp)).all()

                return [
                    {
                        "id": record.id,
                        "jurisdiction": record.jurisdiction,
                        "timestamp": record.timestamp.isoformat() if record.timestamp else None,
                        "total_routes": record.total_routes,
                        "valid_routes": record.valid_routes,
                        "success_rate": round(record.success_rate, 1),
                        "processing_time": round(record.processing_time_seconds, 2)
                    }
                    for record in records
                ]

        except Exception as e:
            print(f"Error getting recent analyses: {e}")
            return []

    def clear_old_history(self, days: int = 90) -> int:
        """
        Clear analysis history older than specified days.

        Args:
            days: Number of days to keep

        Returns:
            Number of records deleted
        """
        try:
            with self.db_manager.get_session() as db:
                cutoff_date = datetime.utcnow() - timedelta(days=days)

                old_records = db.query(AnalysisHistoryModel).filter(
                    AnalysisHistoryModel.timestamp < cutoff_date
                ).all()

                count = len(old_records)
                for record in old_records:
                    db.delete(record)

                db.commit()
                return count

        except Exception as e:
            print(f"Error clearing old history: {e}")
            return 0
