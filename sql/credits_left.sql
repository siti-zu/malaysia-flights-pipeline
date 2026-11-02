SELECT credits_left, run_at
FROM raw.api_runs
WHERE credits_left IS NOT NULL
ORDER BY run_at DESC
LIMIT 1;