"""
Utilidades para instrumentación de performance de endpoints.
Mide tiempos de ejecución de endpoints y queries SQL.
"""
import time
import logging
from functools import wraps
from typing import Callable, Any
from contextlib import contextmanager
from collections import defaultdict
import threading

logger = logging.getLogger(__name__)

# Almacenamiento thread-safe de métricas
_metrics_lock = threading.Lock()
_endpoint_metrics = defaultdict(list)  # {endpoint_name: [durations]}
_query_metrics = defaultdict(list)     # {endpoint_name: [(query_desc, duration)]}


class TimingContext:
    """Contexto para medir tiempos de operaciones."""

    def __init__(self, operation: str):
        self.operation = operation
        self.start_time = None
        self.duration = None

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.duration = time.perf_counter() - self.start_time
        logger.info(f"⏱️  {self.operation}: {self.duration*1000:.2f}ms")
        return False


def measure_endpoint(endpoint_name: str = None):
    """
    Decorador para medir tiempo total de un endpoint.

    Uso:
        @measure_endpoint("metrics_cards")
        def metrics_cards(...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        name = endpoint_name or func.__name__

        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()

            logger.info(f"\n{'='*60}")
            logger.info(f"🚀 START: {name}")
            logger.info(f"{'='*60}")

            try:
                result = func(*args, **kwargs)
                duration = time.perf_counter() - start_time

                # Almacenar métrica
                with _metrics_lock:
                    _endpoint_metrics[name].append(duration)

                logger.info(f"{'='*60}")
                logger.info(f"✅ END: {name} - Total: {duration*1000:.2f}ms ({duration:.3f}s)")
                logger.info(f"{'='*60}\n")

                return result

            except Exception as e:
                duration = time.perf_counter() - start_time
                logger.error(f"❌ ERROR in {name} after {duration*1000:.2f}ms: {str(e)}")
                raise

        return wrapper
    return decorator


@contextmanager
def measure_query(query_description: str, endpoint_name: str = None):
    """
    Context manager para medir tiempo de una query SQL.

    Uso:
        with measure_query("Count APSA abiertos", "metrics_cards"):
            result = db.execute(query).scalar()
    """
    start_time = time.perf_counter()
    query_number = _get_query_count(endpoint_name) + 1

    logger.info(f"  📊 Query #{query_number}: {query_description}")

    try:
        yield
        duration = time.perf_counter() - start_time

        # Almacenar métrica
        if endpoint_name:
            with _metrics_lock:
                _query_metrics[endpoint_name].append((query_description, duration))

        logger.info(f"     ⏱️  Completed in {duration*1000:.2f}ms")

    except Exception as e:
        duration = time.perf_counter() - start_time
        logger.error(f"     ❌ Query failed after {duration*1000:.2f}ms: {str(e)}")
        raise


def _get_query_count(endpoint_name: str = None) -> int:
    """Retorna el número actual de queries para un endpoint."""
    if not endpoint_name:
        return 0
    with _metrics_lock:
        return len(_query_metrics.get(endpoint_name, []))


def get_endpoint_stats(endpoint_name: str) -> dict:
    """
    Obtiene estadísticas de un endpoint específico.

    Returns:
        {
            "calls": int,
            "total_time_ms": float,
            "avg_time_ms": float,
            "min_time_ms": float,
            "max_time_ms": float,
            "queries": [
                {"description": str, "time_ms": float},
                ...
            ]
        }
    """
    with _metrics_lock:
        durations = _endpoint_metrics.get(endpoint_name, [])
        queries = _query_metrics.get(endpoint_name, [])

        if not durations:
            return {
                "calls": 0,
                "total_time_ms": 0,
                "avg_time_ms": 0,
                "min_time_ms": 0,
                "max_time_ms": 0,
                "queries": []
            }

        durations_ms = [d * 1000 for d in durations]

        # Tomar queries de la última ejecución
        last_queries = []
        if queries:
            # Asumimos que las queries se acumulan, tomamos las últimas
            query_count = len(queries) // len(durations)
            last_queries = queries[-query_count:] if query_count > 0 else queries

        return {
            "calls": len(durations),
            "total_time_ms": sum(durations_ms),
            "avg_time_ms": sum(durations_ms) / len(durations_ms),
            "min_time_ms": min(durations_ms),
            "max_time_ms": max(durations_ms),
            "last_execution_queries": [
                {"description": desc, "time_ms": dur * 1000}
                for desc, dur in last_queries
            ]
        }


def get_all_stats() -> dict:
    """Obtiene estadísticas de todos los endpoints instrumentados."""
    with _metrics_lock:
        endpoint_names = set(_endpoint_metrics.keys()) | set(_query_metrics.keys())

        return {
            name: get_endpoint_stats(name)
            for name in sorted(endpoint_names)
        }


def reset_stats():
    """Limpia todas las estadísticas acumuladas."""
    with _metrics_lock:
        _endpoint_metrics.clear()
        _query_metrics.clear()
    logger.info("📊 Performance stats reset")


def print_summary(endpoint_name: str = None):
    """
    Imprime un resumen de estadísticas en los logs.

    Args:
        endpoint_name: Si se especifica, solo muestra ese endpoint.
                      Si es None, muestra todos.
    """
    if endpoint_name:
        stats = {endpoint_name: get_endpoint_stats(endpoint_name)}
    else:
        stats = get_all_stats()

    logger.info("\n" + "="*80)
    logger.info("📊 PERFORMANCE SUMMARY")
    logger.info("="*80)

    for name, data in stats.items():
        if data["calls"] == 0:
            continue

        logger.info(f"\n🎯 Endpoint: {name}")
        logger.info(f"   Calls: {data['calls']}")
        logger.info(f"   Average: {data['avg_time_ms']:.2f}ms")
        logger.info(f"   Min: {data['min_time_ms']:.2f}ms")
        logger.info(f"   Max: {data['max_time_ms']:.2f}ms")
        logger.info(f"   Total: {data['total_time_ms']:.2f}ms")

        if data['last_execution_queries']:
            logger.info(f"\n   Last Execution Queries ({len(data['last_execution_queries'])}):")
            for i, q in enumerate(data['last_execution_queries'], 1):
                logger.info(f"     {i}. {q['description']}: {q['time_ms']:.2f}ms")

    logger.info("\n" + "="*80 + "\n")
