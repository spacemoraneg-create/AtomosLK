"""
Atomos Database Module (Fold 2)

Provides database connection, schema initialization, and repository functions.
"""

from atomos.database.connection import get_connection, initialize_database

__all__ = ["get_connection", "initialize_database"]
