
WITH source AS (
    SELECT * FROM {{ source('raw', 'flights') }}
),

renamed AS (
    SELECT
        airport,
        direction,
        query_date,
        run_id,
        LOWER(payload->>'icao24') AS icao24,
        NULLIF(TRIM(payload->>'callsign'), '') AS callsign,
        to_timestamp((payload->>'firstSeen')::bigint) AS first_seen,
        to_timestamp((payload->>'lastSeen')::bigint) AS last_seen,
        payload->>'estArrivalAirport' AS est_arrival_airport,
        payload->>'estDepartureAirport' AS est_departure_airport,
        (payload->>'arrivalAirportCandidatesCount')::integer AS arrival_airport_candidates_count,
        (payload->>'estArrivalAirportVertDistance')::numeric AS est_arrival_airport_vert_distance,
        (payload->>'estArrivalAirportHorizDistance')::numeric AS est_arrival_airport_horiz_distance,
        (payload->>'departureAirportCandidatesCount')::integer AS departure_airport_candidates_count,
        (payload->>'estDepartureAirportVertDistance')::numeric AS est_departure_airport_vert_distance,
        (payload->>'estDepartureAirportHorizDistance')::numeric AS est_departure_airport_horiz_distance
    FROM source
)

SELECT
    airport,
    direction,
    query_date,
    run_id,
    icao24,
    callsign,
    LEFT(callsign, 3) AS airline_code,
    first_seen,
    last_seen,
    est_arrival_airport,
    est_departure_airport,
    arrival_airport_candidates_count,
    est_arrival_airport_vert_distance,
    est_arrival_airport_horiz_distance,
    departure_airport_candidates_count,
    est_departure_airport_vert_distance,
    est_departure_airport_horiz_distance
FROM renamed