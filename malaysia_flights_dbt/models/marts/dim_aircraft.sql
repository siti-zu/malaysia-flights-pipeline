SELECT
    icao24,
    registration,
    aircraft_manufacturer,
    aircraft_model,
    aircraft_type_code,
    operator,
    operator_icao
FROM {{ ref('stg_aircraft') }}
