"""Draw the README's result charts from the reporting marts.

Writes a light and a dark SVG for each chart to docs/images/, so GitHub can show
the one that matches the reader's theme. Run `make transform` first.

Usage:
    python -m scripts.build_readme_charts  (from the repo root)
"""

from html import escape
from pathlib import Path

from ingestion.load import get_connection

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "images"
FONT = '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif'
THEMES = {
    "light": {"bar": "#2a78d6", "text": "#0b0b0b", "secondary": "#52514e", "muted": "#6f6d68", "grid": "#e1e0d9", "axis": "#c3c2b7"},
    "dark": {"bar": "#3987e5", "text": "#f0efec", "secondary": "#c3c2b7", "muted": "#a3a29a", "grid": "#2c2c2a", "axis": "#383835"},
}
WIDTH = 760

AIRPORT_LABELS = {"WMKK": "KLIA", "WMSA": "Subang", "WMKP": "Penang", "WBKK": "Kota Kinabalu"}
# OpenFlights has a Libyan airline for this code, but these are Malaysian aircraft.
AIRLINE_LABELS = {"BNE": "BNE (operator unconfirmed)"}


def text(x, y, content, fill, size=13, anchor="start", weight=400):
    return (
        f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" font-weight="{weight}" '
        f'text-anchor="{anchor}">{escape(content)}</text>'
    )


def bar_right(x, y, length, height, fill, radius=4):
    """A horizontal bar anchored at x, with its far end rounded."""
    r = min(radius, length, height / 2)
    return (
        f'<path fill="{fill}" d="M{x} {y}h{length - r:.1f}q{r} 0 {r} {r}v{height - 2 * r}'
        f'q0 {r} -{r} {r}h-{length - r:.1f}z"/>'
    )


def bar_up(x, baseline, width, length, fill, radius=2):
    """A vertical bar anchored at the baseline, with its top rounded."""
    r = min(radius, length, width / 2)
    return (
        f'<path fill="{fill}" d="M{x:.1f} {baseline}v-{length - r:.1f}q0 -{r} {r} -{r}h{width - 2 * r:.1f}'
        f'q{r} 0 {r} {r}v{length - r:.1f}z"/>'
    )


def svg(height, description, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {height}" width="{WIDTH}" height="{height}" '
        f'role="img" aria-label="{escape(description, quote=True)}" font-family=\'{FONT}\'>'
        + "".join(body)
        + "</svg>\n"
    )


def ranked_bars(theme, title, subtitle, rows, description):
    """Ranked horizontal bars. rows is a list of (label, value, value_label)."""
    colors = THEMES[theme]
    left, top, row_height, bar_height = 250, 62, 30, 18
    plot_width = WIDTH - left - 125
    largest = max(value for _, value, _ in rows)

    body = [
        text(0, 20, title, colors["text"], size=16, weight=600),
        text(0, 42, subtitle, colors["secondary"]),
    ]
    for i, (label, value, value_label) in enumerate(rows):
        y = top + i * row_height
        middle = y + bar_height / 2 + 4.5
        length = plot_width * value / largest
        body.append(text(left - 12, middle, label, colors["text"], anchor="end"))
        body.append(bar_right(left, y, length, bar_height, colors["bar"]))
        body.append(text(left + length + 8, middle, value_label, colors["secondary"]))
    bottom = top + len(rows) * row_height - (row_height - bar_height)
    body.append(f'<path stroke="{colors["axis"]}" d="M{left} {top - 6}V{bottom + 6}"/>')
    return svg(bottom + 10, description, body)


def nice_ticks(largest):
    """Two round y-axis values at or below the largest value."""
    for step in (1, 2, 5, 10, 20, 50, 100):
        if largest / step <= 2.5:
            return [step, step * 2] if step * 2 <= largest else [step]
    return [largest]


def hour_panel(colors, x, y, width, height, title, hours):
    """One airport's 24 hours as columns, with its own y scale and the peak labelled."""
    left, top, bottom = 24, 44, 22
    plot_width = width - left
    baseline = y + height - bottom
    plot_height = height - top - bottom
    largest = max(value for _, value in hours)
    slot = plot_width / 24

    body = [text(x, y + 16, title, colors["text"], size=14, weight=600)]
    for tick in nice_ticks(largest):
        tick_y = baseline - plot_height * tick / largest
        body.append(f'<path stroke="{colors["grid"]}" d="M{x + left} {tick_y:.1f}H{x + width}"/>')
        body.append(text(x + left - 6, tick_y + 4, str(tick), colors["muted"], size=11, anchor="end"))
    for hour, value in hours:
        if value > 0:
            length = max(plot_height * value / largest, 1)
            body.append(bar_up(x + left + hour * slot + 1, baseline, slot - 2, length, colors["bar"]))
    body.append(f'<path stroke="{colors["axis"]}" d="M{x + left} {baseline}H{x + width}"/>')
    for hour in (0, 6, 12, 18):
        body.append(text(x + left + (hour + 0.5) * slot, baseline + 16, f"{hour:02d}:00", colors["muted"], size=11, anchor="middle"))

    # Hours can tie, as Penang's do, so label every peak hour.
    peak_hours = [hour for hour, value in hours if value == largest]
    peak_label = " and ".join(f"{hour:02d}:00" for hour in peak_hours)
    peak_x = x + left + (peak_hours[0] + 0.5) * slot
    anchor = "end" if peak_hours[0] > 18 else "start" if peak_hours[0] < 5 else "middle"
    body.append(text(peak_x, baseline - plot_height - 6, f"{peak_label}: {largest} a day", colors["secondary"], size=12, anchor=anchor))
    return body


def busiest_hours(theme, airports, description):
    """Small multiples, one panel per airport. airports is a list of (title, hours)."""
    colors = THEMES[theme]
    gap, panel_height, top = 40, 190, 62
    panel_width = (WIDTH - gap) / 2
    body = [
        text(0, 20, "KLIA and Kota Kinabalu are busiest at 15:00", colors["text"], size=16, weight=600),
        text(0, 42, "Average movements per day by hour, Malaysia time. Each panel has its own scale.", colors["secondary"]),
    ]
    for i, (title, hours) in enumerate(airports):
        x = (i % 2) * (panel_width + gap)
        y = top + (i // 2) * (panel_height + 16)
        body += hour_panel(colors, x, y, panel_width, panel_height, title, hours)
    return svg(top + 2 * panel_height + 16, description, body)


def fetch(conn, query):
    return conn.execute(query).fetchall()


def route_label(code, city):
    # OurAirports sometimes adds a district, e.g. "Manila (Pasay)".
    return AIRPORT_LABELS.get(code) or city.split(" (")[0]


def main() -> None:
    with get_connection() as conn:
        routes = fetch(conn, """
            SELECT departure_airport_code, departure_city, arrival_airport_code, arrival_city, flights
            FROM analytics.rpt_top_routes ORDER BY route_rank, route LIMIT 10
        """)
        airlines = fetch(conn, """
            SELECT airline_code, airline_name, flights, share_of_flights_pct
            FROM analytics.rpt_flights_per_airline
            WHERE airline_code IS NOT NULL ORDER BY airline_rank LIMIT 10
        """)
        hours = fetch(conn, """
            SELECT airport_code, hour_of_day, avg_movements_per_day
            FROM analytics.rpt_busiest_hours ORDER BY airport_code, hour_of_day
        """)

    # Bangkok has two airports in the top routes, so a city name alone can be ambiguous.
    codes_by_city = {}
    for row in routes:
        codes_by_city.setdefault(row[1], set()).add(row[0])
        codes_by_city.setdefault(row[3], set()).add(row[2])

    def place(code, city):
        label = route_label(code, city)
        return f"{label} ({code})" if len(codes_by_city[city]) > 1 and code not in AIRPORT_LABELS else label

    route_rows = [(f"{place(r[0], r[1])} → {place(r[2], r[3])}", r[4], f"{r[4]:,}") for r in routes]
    route_text = "Top 10 routes by flights: " + "; ".join(f"{label}, {shown}" for label, _, shown in route_rows)

    airline_rows = [
        (AIRLINE_LABELS.get(code, name or code), flights, f"{flights:,} ({share:.1f}%)")
        for code, name, flights, share in airlines
    ]
    airline_text = "Top 10 airlines by flights: " + "; ".join(f"{label}, {shown}" for label, _, shown in airline_rows)

    by_airport = {}
    for code, hour, average in hours:
        by_airport.setdefault(code, []).append((hour, float(average)))
    # Busiest airport first.
    ordered = sorted(by_airport, key=lambda code: -max(v for _, v in by_airport[code]))
    panels = [(f"{AIRPORT_LABELS[code]} ({code})", by_airport[code]) for code in ordered]
    hours_text = "Average movements per day by hour. Peaks: " + "; ".join(
        "{}: {:02d}:00, {}".format(title, *max(values, key=lambda item: item[1])) for title, values in panels
    )

    # The chart titles state findings from the current data, so re-check them after a refresh.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        charts = {
            "top_routes": ranked_bars(
                theme, "Singapore to KLIA is the busiest route seen",
                "Top 10 routes where both airports are known. KLIA departures are under-counted, so routes into KLIA dominate.", route_rows, route_text,
            ),
            "busiest_hours": busiest_hours(theme, panels, hours_text),
            "flights_per_airline": ranked_bars(
                theme, "AirAsia and Malaysia Airlines fly over half of all flights",
                "Flights and share of all flights, top 10 airlines", airline_rows, airline_text,
            ),
        }
        for name, content in charts.items():
            (OUTPUT_DIR / f"{name}_{theme}.svg").write_text(content, encoding="utf-8")
    print(f"Wrote {len(THEMES) * 3} charts to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
