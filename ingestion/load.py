from ingestion.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
import psycopg
from psycopg.types.json import Jsonb

def get_connection():
    """Open a connection to the pipeline database.

    Autocommit is on, so each write commits on its own unless it is wrapped
    in conn.transaction(). Raises psycopg.OperationalError if unreachable.
    """
    return psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        autocommit=True,
    )

def load_flights(conn, flights, airport, direction, query_date, run_id):
    # One transaction per partition: the delete and insert succeed or fail together,
    # and a failure rolls back without leaving the connection unusable.
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM raw.flights
            WHERE airport = %s AND direction = %s AND query_date = %s
            """,
            (airport, direction, query_date)
        )
        cur.executemany(
            """
            INSERT INTO raw.flights (airport, direction, query_date, payload, run_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [(airport, direction, query_date, Jsonb(flight), run_id) for flight in flights]
        )

    return len(flights)

def log_api_run(conn, airport, direction, query_date, run_id, status_code=None,
                row_count=None, credits_left=None, error_message=None):
    conn.execute(
        """
        INSERT INTO raw.api_runs
            (airport, direction, query_date, status_code, row_count, credits_left, error_message, run_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (airport, direction, query_date, status_code, row_count, credits_left, error_message, run_id)
    )
