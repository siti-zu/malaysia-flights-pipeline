WITH flights AS (
  SELECT * FROM {{ ref('stg_flights') }}
  WHERE icao24 IS NOT NULL
    AND first_seen IS NOT NULL
),
numbered AS (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY icao24, first_seen ORDER BY query_date DESC, direction DESC) AS copy_number
  FROM flights
),
deduped AS (
  SELECT *
  FROM numbered
  WHERE copy_number = 1
)

SELECT 
    md5(CONCAT(icao24, '|',EXTRACT(EPOCH FROM first_seen)::bigint)) AS flight_id,
    run_id,
    icao24,
    callsign,
    airline_code,
    (first_seen AT TIME ZONE 'Asia/Kuala_Lumpur')::date AS flight_date,
    first_seen,
    last_seen,
    first_seen AT TIME ZONE 'Asia/Kuala_Lumpur' AS first_seen_local,
    last_seen AT TIME ZONE 'Asia/Kuala_Lumpur' AS last_seen_local,
    round(EXTRACT(EPOCH FROM last_seen - first_seen) / 60) AS flight_duration_minutes,
    est_departure_airport,
    est_arrival_airport,
    est_departure_airport || '-' || est_arrival_airport AS route,
    departure_airport_candidates_count,
    arrival_airport_candidates_count,
    est_departure_airport_vert_distance,
    est_departure_airport_horiz_distance,
    est_arrival_airport_vert_distance,
    est_arrival_airport_horiz_distance
FROM deduped