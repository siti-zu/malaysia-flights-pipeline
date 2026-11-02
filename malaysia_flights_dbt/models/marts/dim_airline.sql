SELECT
    airline_code,
    airline_name
FROM {{ ref('stg_airlines') }}
