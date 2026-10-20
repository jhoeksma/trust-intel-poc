from app.sources.loaders import load_generic, load_rtt


def csv(*lines):
    return ("\n".join(lines) + "\n").encode()


def test_long_format_nof():
    data = csv("Org Code,Org Name,Period,Metric ID,Metric Name,Metric Value",
               "RXX,Alpha Trust,Q1 2026/27,OF5000,Segment,2",
               "RXX,Alpha Trust,Q4 2025/26,OF5000,Segment,3",
               "RYY,Beta Trust,Q1 2026/27,OF5000,Segment,4")
    r = load_generic("nof", "trust-data.csv", data)
    assert r.profile["shape"] == "long"
    assert len(r.metrics) == 3 and set(r.orgs) == {"RXX", "RYY"}
    assert {m["period"] for m in r.metrics} == {"Q1 2026/27", "Q4 2025/26"}
    assert r.metrics[0]["metric_code"] == "nof:of5000"


def test_wide_format_with_suppression_markers():
    data = csv("Trust Code,Trust Name,Energy cost,Backlog maintenance,Notes",
               "RXX,Alpha,\"1,200\",*,hello",
               "RYY,Beta,300,45,there",
               "RZZ,Gamma,400,50,again")
    r = load_generic("eric", "ERIC - 2024_25 - Trust data.csv", data)
    codes = {m["metric_code"] for m in r.metrics}
    assert "eric:energy_cost" in codes and "eric:notes" not in codes
    assert all(m["period"] == "2024/25" for m in r.metrics)
    assert [m["value"] for m in r.metrics if m["ods_code"] == "RXX"] == [1200.0]  # '*' dropped


def test_no_org_column_is_profile_only():
    r = load_generic("x", "f.csv", csv("a,b", "1,2", "3,4"))
    assert r.metrics == [] and r.mapper_status == "needs_review"


def test_rtt_aggregation():
    hdr = ("Period,Provider Org Code,Provider Org Name,Commissioner Org Code,RTT Part Type,Treatment Function Code,"
           "Gt 00 To 01 Weeks SUM 1,Gt 17 To 18 Weeks SUM 1,Gt 18 To 19 Weeks SUM 1,Gt 52 Weeks SUM 1,Total All")
    data = csv(hdr,
               "RTT-April-2026,RXX,Alpha,AAA,Part_2,C_999,50,10,20,20,100",
               "RTT-April-2026,RXX,Alpha,BBB,Part_2,C_999,30,10,0,10,50",
               "RTT-April-2026,RXX,Alpha,BBB,Part_1A,C_999,999,0,0,0,999",
               "RTT-April-2026,RXX,Alpha,BBB,Part_2,C_100,999,0,0,0,999")
    r = load_rtt("rtt", "rtt.csv", data)
    got = {m["metric_code"]: m["value"] for m in r.metrics}
    assert got["rtt:incomplete_pathways_total"] == 150
    assert got["rtt:incomplete_over_18_weeks"] == 50
    assert got["rtt:pct_within_18_weeks"] == round(100 * 100 / 150, 2)
    assert r.mapper_status == "ok"


def test_rtt_unexpected_columns_fall_back():
    r = load_rtt("rtt", "rtt.csv", csv("Org Code,Value", "RXX,1", "RYY,2", "RZZ,3"))
    assert r.mapper_status == "needs_review"


WF_HDR = "DATA_MONTH,ORG_CODE,ORG_NAME,MAIN_STAFF_GROUP,STAFF_GROUP_1,FTE"


def test_workforce_dimensions_are_summed_not_collapsed():
    data = csv(WF_HDR,
               "2026-07-31,RXX,Alpha,Nurses,A,10",
               "2026-07-31,RXX,Alpha,Nurses,B,5.5",
               "2026-07-31,RXX,Alpha,Doctors,C,4",
               "2026-07-31,RYY,Beta,Nurses,A,7")
    r = load_generic("workforce", "Core 8. NWD Staff Group - org, Jul-26.csv", data)
    got = {(m["ods_code"], m["metric_code"]): m["value"] for m in r.metrics}
    assert got[("RXX", "workforce:core_8:fte")] == 19.5
    assert got[("RXX", "workforce:core_8:fte:nurses")] == 15.5
    assert got[("RXX", "workforce:core_8:fte:doctors")] == 4
    assert got[("RYY", "workforce:core_8:fte")] == 7
    keys = [(m["ods_code"], m["metric_code"], m["period"]) for m in r.metrics]
    assert len(keys) == len(set(keys))  # one value per org, metric, period
    assert r.profile["breakdown_column"] == "MAIN_STAFF_GROUP"


def test_url_encoded_file_name_still_gives_period():
    data = csv("Trust Code,Trust Name,Energy cost", "RXX,Alpha,5", "RYY,Beta,6", "RZZ,Gamma,7")
    r = load_generic("eric", "ERIC%20-%202024_25%20-%20Trust%20data.csv", data)
    assert {m["period"] for m in r.metrics} == {"2024/25"}


def test_long_file_counts_suppressed_values():
    data = csv("ORG_CODE,ORG_DESCRIPTION,REPORTING_PERIOD,MEASURE_TYPE,MEASURE,MEASURE_VALUE",
               "RXX,Alpha,2425,Summary,FAE_SUM,100",
               "RYY,Beta,2425,Summary,FAE_SUM,*",
               "RZZ,Gamma,2425,Summary,FAE_SUM,50")
    r = load_generic("hes", "hosp-epis-stat-admi-pla-2024-25.csv", data)
    assert r.profile["suppressed_values"] == 1 and len(r.metrics) == 2
    assert "[Summary]" in r.metrics[0]["metric_label"]
