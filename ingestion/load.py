from ingestion.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
import psycopg
from psycopg.types.json import Jsonb

def get_connection():
    """Open a connection to the pipeline database."""
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )

def load_flights(flights, airport, direction, query_date):
    with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM raw.flights 
                WHERE airport = %s AND direction = %s AND query_date = %s
                """,
                (airport, direction, query_date)
            )
            cur.executemany(
                """
                INSERT INTO raw.flights (airport, direction, query_date, payload) 
                VALUES (%s, %s, %s, %s)
                """,
                [(airport, direction, query_date, Jsonb(flight)) for flight in flights]
            )

    return len(flights)

def log_api_run(airport, direction, query_date, status_code=None,
                row_count=None, credits_left=None, error_message=None):
    with get_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO raw.api_runs 
                    (airport, direction, query_date, status_code, row_count, credits_left, error_message) 
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (airport, direction, query_date, status_code, row_count, credits_left, error_message)
            )
