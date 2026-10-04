from ingestion.config import DB_HOST, DB_NAME, DB_PASSWORD, DB_PORT, DB_USER
import psycopg
from psycopg.types.json import Jsonb

def load_flights(flights, airport, direction, query_date):
    with psycopg.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    ) as conn:
        with conn.cursor() as cur:
            # delete existing rows in raw.flights for that airport, direction and date
            cur.execute(
                "DELETE FROM raw.flights WHERE airport = %s AND direction = %s AND query_date = %s",
                (airport, direction, query_date)
            )
            # insert one row per flight, with the whole flight object in payload
            cur.executemany(
                "INSERT INTO raw.flights (airport, direction, query_date, payload) VALUES (%s, %s, %s, %s)",
                [(airport, direction, query_date, Jsonb(flight)) for flight in flights]
            )

    return len(flights)
