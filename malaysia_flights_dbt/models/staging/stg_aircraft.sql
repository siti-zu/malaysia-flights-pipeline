SELECT
    LOWER(icao24)::text AS icao24,
    registration::text AS registration,
    manufacturer::text AS aircraft_manufacturer,
    model::text AS aircraft_model,
    typecode::text AS aircraft_type_code,
    operator::text AS operator,
    operator_icao::text AS operator_icao
FROM {{ ref('aircraft') }}