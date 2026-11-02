-- Every query_date should have a successful call for all 4 airports x 2
-- directions = 8 slices. Returns each date that doesn't, with how many it has.
--
-- 404 counts as success: OpenSky returns it when an airport had no flights
-- that day, and ingestion stores it as an empty result. Slices are counted
-- distinctly, so a call that failed and later succeeded on a re-run passes.
-- Dates with no calls at all are included too, so a skipped day fails.

WITH successful_slices AS (
    SELECT
        query_date,
        COUNT(DISTINCT (airport, direction)) AS successful_calls
    FROM {{ source('raw', 'api_runs') }}
    WHERE status_code IN (200, 404)
    GROUP BY query_date
),

all_dates AS (
    SELECT generate_series(MIN(query_date), MAX(query_date), interval '1 day')::date AS query_date
    FROM {{ source('raw', 'api_runs') }}
)

SELECT
    all_dates.query_date,
    COALESCE(successful_slices.successful_calls, 0) AS successful_calls
FROM all_dates
LEFT JOIN successful_slices USING (query_date)
WHERE COALESCE(successful_slices.successful_calls, 0) < 8
ORDER BY all_dates.query_date
