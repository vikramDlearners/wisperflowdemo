"""Overview: money to keep aside for next month, from stock in hand, price and how long the course runs."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.services import doses as doses_svc

from tests.test_family_dashboard import _get, dashboard_setup  # noqa: F401


def _estimate(client, db_session, s):
    r = _get(client, db_session, s["manager"], s["family"].id)
    assert r.status_code == 200, r.text
    est = r.json()["next_month_estimate"]
    return est, {i["display_name"]: i for i in est["items"]}


def _today(s):
    return doses_svc.today_for(s["appa"], datetime.now(timezone.utc))


def test_only_the_shortfall_after_stock_is_priced(client, db_session, dashboard_setup):
    s = dashboard_setup
    s["amlodipine"].unit_price = Decimal("5.00")  # 14 in stock, 2 a day
    s["metformin"].unit_price = Decimal("2.00")  # 30 in stock, 1 a day
    db_session.commit()

    est, items = _estimate(client, db_session, s)

    a = items["Amlodipine"]
    assert (a["doses_per_day"], a["days_needed"], a["tablets_needed"], a["in_stock"], a["to_buy"], a["cost"]) == (
        2, 30, 60, 14, 46, 230.0)
    m = items["Metformin"]
    assert (m["to_buy"], m["cost"]) == (0, 0.0)  # stock already covers the month
    v = items["Vitamin D"]
    assert (v["in_stock"], v["to_buy"], v["cost"]) == (None, 30, None)
    assert (est["amount"], est["days"], est["priced_count"], est["unpriced_count"]) == (230.0, 30, 2, 1)


def test_a_course_ending_soon_needs_only_its_remaining_days(client, db_session, dashboard_setup):
    s = dashboard_setup
    s["amlodipine"].unit_price = Decimal("5.00")
    s["amlodipine"].take_until = _today(s) + timedelta(days=9)  # today plus 9 more days
    s["metformin"].unit_price = Decimal("2.00")
    s["metformin"].quantity_remaining = 0
    s["metformin"].take_until = _today(s) - timedelta(days=1)  # course already over
    db_session.commit()

    est, items = _estimate(client, db_session, s)

    a = items["Amlodipine"]
    assert (a["days_needed"], a["tablets_needed"], a["to_buy"], a["cost"]) == (10, 20, 6, 30.0)
    assert a["take_until"] == (_today(s) + timedelta(days=9)).isoformat()
    m = items["Metformin"]
    assert (m["days_needed"], m["to_buy"], m["cost"]) == (0, 0, 0.0)
    assert est["amount"] == 30.0


def test_a_course_longer_than_a_month_counts_one_month(client, db_session, dashboard_setup):
    s = dashboard_setup
    s["amlodipine"].unit_price = Decimal("1.50")
    s["amlodipine"].take_until = _today(s) + timedelta(days=90)
    db_session.commit()
    _, items = _estimate(client, db_session, s)
    assert (items["Amlodipine"]["days_needed"], items["Amlodipine"]["cost"]) == (30, 69.0)


def test_no_prices_means_no_amount(client, db_session, dashboard_setup):
    est, items = _estimate(client, db_session, dashboard_setup)
    assert est["amount"] is None
    assert est["unpriced_count"] == 2  # Metformin's stock covers the month, so its missing price doesn't matter
    assert items["Amlodipine"]["to_buy"] == 46


def test_take_until_can_be_set_and_cleared(client, db_session, dashboard_setup):
    from tests.test_family_dashboard import _auth
    s = dashboard_setup
    url = f"/api/families/{s['family'].id}/medicines/{s['amlodipine'].id}"
    h = _auth(db_session, s["manager"])
    r = client.patch(url, json={"take_until": "2026-12-31"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["take_until"] == "2026-12-31"
    assert client.patch(url, json={"take_until": None}, headers=h).json()["take_until"] is None
