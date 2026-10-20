from app.sources.eric_site import load_eric_site

HEAD1 = ",".join([""] * 15 + ["S03_08", "S03_10", "S02_01", "S02_03", "S01_17", "S05_19", "S02_13J", "S01_19"])
HEAD2 = ",".join(["Trust Code", "Trust Name", "Region", "Trust Type", "Id", "Site Code", "Site Name", "Post", "ICB", "LA",
                  "Site Type", "Tenure", "x", "y", "UPRN",
                  "Cost to eradicate high risk backlog (£)", "Cost to eradicate moderate risk backlog (£)",
                  "Gross internal floor area (m²)", "Occupied floor area (m²)",
                  "Not functionally suitable - occupied floor area (m²)", "Gas costs (£)", "Age profile - 1995 to 2004 (%)",
                  "Floor area - empty (m²)"])


def row(org, st, *vals):
    return ",".join([org, "Trust " + org, "R", "T", "1", "S", "Site", "P", "I", "L", st, "Freehold", "", "", "9"] + [str(v) for v in vals])


def make(*rows):
    return ("\n".join([HEAD1, HEAD2, *rows]) + "\n").encode()


def got(r):
    return {(m["ods_code"], m["metric_code"]): m["value"] for m in r.metrics}


def test_sites_roll_up_to_trust():
    data = make(row("RXX", "Acute", 100, 300, 1000, 900, 90, 50, 100, 0),
                row("RXX", "Non inpatient", 0, 100, 3000, 2700, 270, 150, 0, 300),
                row("RYY", "Acute", 10, 10, 500, "Not Applicable", "", 5, 50, 0))
    r = load_eric_site("eric_site", "ERIC - 2025_26 - Site data.csv", data)
    g = got(r)
    assert g[("RXX", "eric_site:s03_08")] == 100 and g[("RXX", "eric_site:s03_10")] == 400
    assert g[("RXX", "eric_site:backlog_total")] == 500
    assert g[("RXX", "eric_site:backlog_per_sqm")] == 500 / 4000
    assert g[("RXX", "eric_site:sites_total")] == 2 and g[("RXX", "eric_site:sites:acute")] == 1
    assert g[("RXX", "eric_site:energy_cost_total")] == 200
    assert g[("RXX", "eric_site:unsuitable_share")] == 100 * 360 / 3600
    assert g[("RXX", "eric_site:empty_share")] == 100 * 300 / 4000
    assert r.profile["file_period"] == "2025/26" and r.mapper_status == "ok"


def test_percentages_are_floor_area_weighted_and_na_is_not_zero():
    data = make(row("RXX", "Acute", 0, 0, 1000, 1000, 0, 0, 100, 0), row("RXX", "Acute", 0, 0, 3000, 3000, 0, 0, 0, 0),
                row("RYY", "Acute", 1, 1, 500, "Not Applicable", "", 5, 50, 0))
    g = got(load_eric_site("eric_site", "ERIC - 2025_26 - Site data.csv", data))
    assert g[("RXX", "eric_site:s02_13j")] == 25.0  # (100*1000 + 0*3000) / 4000
    assert ("RYY", "eric_site:s02_03") not in g  # Not Applicable is missing, not zero
    assert ("RYY", "eric_site:unsuitable_share") not in g
