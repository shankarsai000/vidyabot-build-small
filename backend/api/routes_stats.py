"""
Statistics Routes

GET /api/stats - Cost tracking and analytics dashboard
GET /api/stats/cache - Cache statistics
GET /api/health - Health check endpoint
"""

import logging
from typing import Dict
from fastapi import APIRouter
from backend.database import get_db_connection
from backend.cache.semantic_cache import get_cache
from backend.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/health")
async def health_check() -> Dict:
    """
    Health check endpoint.
    
    Returns:
        JSON with health status
    """
    try:
        # Try database connection
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        
        return {
            "status": "healthy",
            "database": "connected",
            "api_model": settings.MODEL_NAME,
            "cache_enabled": True
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e)
        }


@router.get("/stats")
async def get_statistics() -> Dict:
    """
    Get comprehensive cost tracking and analytics.
    
    Returns:
        JSON with usage statistics and cost savings
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get cost statistics
        cursor.execute("""
            SELECT 
                COUNT(*) as total_queries,
                SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END) as cache_hits,
                SUM(actual_tokens_used) as total_tokens_used,
                SUM(baseline_tokens) as total_baseline_tokens,
                SUM(tokens_saved) as total_tokens_saved,
                SUM(cost_usd) as total_cost_usd,
                SUM((baseline_tokens / 1000000.0) * 0.25) as total_baseline_cost_usd,
                SUM(cost_saved_usd) as total_savings_usd,
                AVG(actual_tokens_used) as avg_tokens_per_query
            FROM cost_log
        """)
        
        row = cursor.fetchone()
        
        total_queries = row[0] or 0
        cache_hits = row[1] or 0
        total_tokens_used = row[2] or 0
        total_baseline_tokens = row[3] or 0
        total_tokens_saved = row[4] or 0
        total_cost = row[5] or 0.0
        baseline_cost = row[6] or 0.0
        total_savings = row[7] or 0.0
        avg_tokens = row[8] or 0
        
        # Get textbook count
        cursor.execute("SELECT COUNT(*) FROM textbooks")
        textbooks_count = cursor.fetchone()[0]
        
        # Calculate metrics
        cache_hit_rate = cache_hits / total_queries if total_queries > 0 else 0.0
        saving_percentage = (total_savings / baseline_cost * 100) if baseline_cost > 0 else 0.0
        
        # Get cache stats
        cache = get_cache()
        cache_stats = cache.get_cache_stats()
        
        return {
            "total_queries": total_queries,
            "cache_hits": cache_hits,
            "cache_hit_rate": cache_hit_rate,
            "total_tokens_used": total_tokens_used,
            "total_baseline_tokens": total_baseline_tokens,
            "total_tokens_saved": total_tokens_saved,
            "total_cost_usd": total_cost,
            "baseline_cost_usd": baseline_cost,
            "total_savings_usd": total_savings,
            "savings_percentage": saving_percentage,
            "avg_tokens_per_query": avg_tokens,
            "textbooks_ingested": textbooks_count,
            "cache_stats": cache_stats,
            "cost_per_query_avg_usd": total_cost / total_queries if total_queries > 0 else 0.0,
            "baseline_cost_per_query_usd": baseline_cost / total_queries if total_queries > 0 else 0.0
        }
        
    except Exception as e:
        logger.error(f"Error getting statistics: {e}")
        return {
            "status": "error",
            "message": str(e),
            "total_queries": 0
        }


@router.get("/stats/cache")
async def get_cache_statistics() -> Dict:
    """
    Get detailed cache statistics.
    
    Returns:
        JSON with cache metrics
    """
    try:
        cache = get_cache()
        stats = cache.get_cache_stats()
        
        return {
            "status": "success",
            **stats
        }
        
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


@router.get("/stats/queries/recent")
async def get_recent_queries(limit: int = 10) -> Dict:
    """
    Get recent queries with their costs.
    
    Args:
        limit: Number of recent queries to return
        
    Returns:
        JSON with recent query logs
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, baseline_tokens, actual_tokens_used, tokens_saved,
                   cost_usd, cost_saved_usd, cache_hit, timestamp
            FROM cost_log
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        
        queries = [
            {
                "id": row[0],
                "baseline_tokens": row[1],
                "actual_tokens_used": row[2],
                "tokens_saved": row[3],
                "cost_usd": row[4],
                "cost_saved_usd": row[5],
                "cache_hit": bool(row[6]),
                "timestamp": row[7]
            }
            for row in rows
        ]
        
        return {
            "status": "success",
            "queries": queries,
            "count": len(queries)
        }
        
    except Exception as e:
        logger.error(f"Error getting recent queries: {e}")
        return {
            "status": "error",
            "message": str(e),
            "queries": []
        }


@router.get("/stats/by-date")
async def get_statistics_by_date() -> Dict:
    """
    Get statistics broken down by date.
    
    Returns:
        JSON with daily aggregated statistics
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                DATE(timestamp) as date,
                COUNT(*) as queries,
                SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END) as cache_hits,
                SUM(tokens_saved) as tokens_saved,
                SUM(cost_saved_usd) as cost_saved_usd
            FROM cost_log
            GROUP BY DATE(timestamp)
            ORDER BY date DESC
        """)
        
        rows = cursor.fetchall()
        
        daily_stats = [
            {
                "date": row[0],
                "queries": row[1],
                "cache_hits": row[2],
                "tokens_saved": row[3],
                "cost_saved_usd": row[4]
            }
            for row in rows
        ]
        
        return {
            "status": "success",
            "daily_stats": daily_stats
        }
        
    except Exception as e:
        logger.error(f"Error getting daily statistics: {e}")
        return {
            "status": "error",
            "message": str(e)
        }
