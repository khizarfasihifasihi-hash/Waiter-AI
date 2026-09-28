"""
FoodOrder Analytics — a Shopify-style sales dashboard built with Streamlit.

Reads confirmed orders from data/orders.json (written by app.py) and shows
orders, revenue, average order value, top products, busiest hours, and more.

Run:
    pip install streamlit pandas plotly
    streamlit run analytics.py
"""
import json
import os
import random
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="FoodOrder Analytics", page_icon="📊", layout="wide")

DEFAULT_ORDERS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "orders.json")
ORANGE = "#f97316"


# =====================================================
# DATA LOADING
# =====================================================
def load_orders(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def make_sample_orders(n=250):
    """Demo data so the dashboard looks alive before real orders exist."""
    menu = [
        ("Classic Cheese Burger", 899), ("Pepperoni Pizza", 1299), ("Spicy Sushi Roll", 750),
        ("Crispy Tacos", 550), ("Garden Salad", 420), ("Chocolate Dessert", 380),
        ("Pasta Alfredo", 980), ("Iced Drink", 250),
    ]
    areas = ["Gulshan", "DHA", "Clifton", "North Nazimabad", "Saddar", "Korangi"]
    rng = random.Random(7)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    orders = []
    for i in range(n):
        days_ago = min(int(rng.expovariate(1 / 12)), 45)
        hour = rng.choices(range(24), weights=[1,1,0,0,0,0,1,2,3,3,4,8,10,8,5,4,5,8,10,10,7,4,2,1])[0]
        placed = (now - timedelta(days=days_ago)).replace(hour=hour, minute=rng.randint(0, 59))
        items = []
        for name, price in rng.sample(menu, rng.randint(1, 3)):
            qty = rng.randint(1, 3)
            items.append({"name": name, "price": price, "qty": qty, "subtotal": price * qty})
        orders.append({
            "order_id": f"SAMPLE-{i + 1}",
            "line_items": items,
            "total": sum(x["subtotal"] for x in items),
            "eta_minutes": rng.randint(20, 45),
            "placed_at": placed.isoformat(),
            "delivery": {"address": rng.choice(areas)},
        })
    return orders


def build_frames(orders, tz):
    """Return (orders_df, items_df) with local-time columns."""
    order_rows, item_rows = [], []
    for o in orders:
        ts = pd.to_datetime(o.get("placed_at"), utc=True, errors="coerce")
        if pd.isna(ts):
            continue
        ts = ts.tz_convert(tz)
        items = o.get("line_items") or o.get("items") or []
        delivery = o.get("delivery") or {}
        order_rows.append({
            "order_id": o.get("order_id"),
            "placed_at": ts,
            "date": ts.date(),
            "hour": ts.hour,
            "weekday": ts.day_name(),
            "total": o.get("total", 0),
            "items_count": sum(i.get("qty", 0) for i in items),
            "eta_minutes": o.get("eta_minutes"),
            "location": (delivery.get("address") or "Not provided").strip() or "Not provided",
            "customer": delivery.get("name") or "",
        })
        for i in items:
            item_rows.append({
                "order_id": o.get("order_id"),
                "date": ts.date(),
                "product": i.get("name"),
                "qty": i.get("qty", 0),
                "revenue": i.get("subtotal", 0),
            })
    return pd.DataFrame(order_rows), pd.DataFrame(item_rows)


def pct_change(current, previous):
    if previous in (0, None):
        return None
    return (current - previous) / previous * 100


def style_fig(fig):
    fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), height=340,
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    return fig


def show_chart(fig):
    """Full-width plotly chart; works on both old and new Streamlit versions."""
    try:
        st.plotly_chart(style_fig(fig), width="stretch")
    except TypeError:
        show_chart(fig)


# =====================================================
# SIDEBAR
# =====================================================
st.sidebar.title("📊 FoodOrder Analytics")
orders_path = st.sidebar.text_input("Orders file", DEFAULT_ORDERS_PATH)
tz = st.sidebar.selectbox("Timezone", ["Asia/Karachi", "UTC", "Asia/Dubai", "Europe/London", "America/New_York"])
use_sample = st.sidebar.toggle("Use sample data", value=False,
                               help="Fill the dashboard with demo orders to preview the charts.")
auto_refresh = st.sidebar.toggle("Auto-refresh every 10s", value=False)
if st.sidebar.button("🔄 Refresh now"):
    st.rerun()

raw_orders = make_sample_orders() if use_sample else load_orders(orders_path)
orders_df, items_df = build_frames(raw_orders, tz)

st.title("Sales overview")

if orders_df.empty:
    st.info("No orders yet. Place an order in the FoodOrder app (or switch on **Use sample data** "
            "in the sidebar) and this dashboard will fill in.")
    st.caption(f"Looking for orders in: `{orders_path}`")
    if auto_refresh:
        import time
        time.sleep(10)
        st.rerun()
    st.stop()

# ---- Date range filter ----
min_d, max_d = orders_df["date"].min(), orders_df["date"].max()
preset = st.sidebar.radio("Date range", ["All time", "Last 7 days", "Last 30 days", "Custom"])
if preset == "Last 7 days":
    start, end = max_d - timedelta(days=6), max_d
elif preset == "Last 30 days":
    start, end = max_d - timedelta(days=29), max_d
elif preset == "Custom":
    picked = st.sidebar.date_input("Range", (min_d, max_d), min_value=min_d, max_value=max_d)
    start, end = (picked if isinstance(picked, tuple) and len(picked) == 2 else (min_d, max_d))
else:
    start, end = min_d, max_d

mask = (orders_df["date"] >= start) & (orders_df["date"] <= end)
f_orders = orders_df[mask]
f_items = items_df[(items_df["date"] >= start) & (items_df["date"] <= end)] if not items_df.empty else items_df

# previous period of equal length, for the % change on KPI cards
span = (end - start).days + 1
prev_start, prev_end = start - timedelta(days=span), start - timedelta(days=1)
prev_orders = orders_df[(orders_df["date"] >= prev_start) & (orders_df["date"] <= prev_end)]

st.caption(f"{start:%d %b %Y} → {end:%d %b %Y}" + ("  ·  ⚠️ sample data" if use_sample else ""))

# =====================================================
# KPI CARDS
# =====================================================
total_orders = len(f_orders)
revenue = f_orders["total"].sum()
aov = revenue / total_orders if total_orders else 0
items_sold = int(f_orders["items_count"].sum())

prev_total = len(prev_orders)
prev_rev = prev_orders["total"].sum()
prev_aov = prev_rev / prev_total if prev_total else 0


def delta(cur, prev):
    p = pct_change(cur, prev)
    return None if p is None else f"{p:+.1f}%"


c1, c2, c3, c4 = st.columns(4)
c1.metric("Total orders", f"{total_orders:,}", delta(total_orders, prev_total))
c2.metric("Revenue", f"Rs {revenue:,.0f}", delta(revenue, prev_rev))
c3.metric("Avg. order value", f"Rs {aov:,.0f}", delta(aov, prev_aov))
c4.metric("Items sold", f"{items_sold:,}")

st.divider()

# =====================================================
# ORDERS + REVENUE OVER TIME
# =====================================================
daily = (f_orders.groupby("date")
         .agg(orders=("order_id", "count"), revenue=("total", "sum"))
         .reindex(pd.date_range(start, end).date, fill_value=0)
         .rename_axis("date").reset_index())

left, right = st.columns(2)
with left:
    fig = px.area(daily, x="date", y="orders", title="Orders over time",
                  color_discrete_sequence=[ORANGE])
    fig.update_traces(line_shape="spline")
    show_chart(fig)
with right:
    fig = px.bar(daily, x="date", y="revenue", title="Revenue over time (Rs)",
                 color_discrete_sequence=["#111827"])
    show_chart(fig)

# =====================================================
# PRODUCTS + PEAK TIMES
# =====================================================
left, right = st.columns(2)
with left:
    if not f_items.empty:
        top = (f_items.groupby("product").agg(units=("qty", "sum"), revenue=("revenue", "sum"))
               .sort_values("units").tail(8).reset_index())
        metric = st.radio("Top products by", ["units", "revenue"], horizontal=True, key="prod_metric")
        fig = px.bar(top.sort_values(metric), x=metric, y="product", orientation="h",
                     title=f"Top products by {metric}", color_discrete_sequence=[ORANGE])
        show_chart(fig)
with right:
    hourly = f_orders.groupby("hour").size().reindex(range(24), fill_value=0).reset_index()
    hourly.columns = ["hour", "orders"]
    fig = px.bar(hourly, x="hour", y="orders", title="Orders by hour of day",
                 color_discrete_sequence=["#111827"])
    fig.update_xaxes(dtick=2)
    show_chart(fig)

left, right = st.columns(2)
with left:
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    heat = (f_orders.groupby(["weekday", "hour"]).size().reset_index(name="orders"))
    if not heat.empty:
        pivot = heat.pivot(index="weekday", columns="hour", values="orders").reindex(days).fillna(0)
        pivot = pivot.reindex(columns=range(24), fill_value=0)
        fig = px.imshow(pivot, aspect="auto", title="When orders come in (day × hour)",
                        color_continuous_scale="Oranges", labels=dict(x="Hour", y="", color="Orders"))
        show_chart(fig)
with right:
    loc = (f_orders.groupby("location").size().sort_values().tail(8).reset_index(name="orders"))
    fig = px.bar(loc, x="orders", y="location", orientation="h",
                 title="Top delivery locations", color_discrete_sequence=[ORANGE])
    show_chart(fig)

# =====================================================
# ORDER VALUE + DELIVERY TIME
# =====================================================
left, right = st.columns(2)
with left:
    fig = px.histogram(f_orders, x="total", nbins=20, title="Order value distribution (Rs)",
                       color_discrete_sequence=["#111827"])
    show_chart(fig)
with right:
    eta = f_orders.dropna(subset=["eta_minutes"])
    if not eta.empty:
        fig = px.histogram(eta, x="eta_minutes", nbins=12, title="Rider ETA distribution (minutes)",
                           color_discrete_sequence=[ORANGE])
        show_chart(fig)
        st.caption(f"Average ETA: **{eta['eta_minutes'].mean():.0f} min**")

# =====================================================
# RECENT ORDERS TABLE + EXPORT
# =====================================================
st.subheader("Recent orders")
table = (f_orders.sort_values("placed_at", ascending=False)
         [["order_id", "placed_at", "customer", "location", "items_count", "total", "eta_minutes"]]
         .rename(columns={"order_id": "Order", "placed_at": "Placed", "customer": "Customer",
                          "location": "Location", "items_count": "Items", "total": "Total (Rs)",
                          "eta_minutes": "ETA (min)"}))
table["Placed"] = table["Placed"].dt.strftime("%d %b %Y %H:%M")
try:
    st.dataframe(table.head(50), width="stretch", hide_index=True)
except TypeError:
    st.dataframe(table.head(50), use_container_width=True, hide_index=True)
st.download_button("⬇️ Download orders as CSV", table.to_csv(index=False).encode("utf-8"),
                   file_name="orders_export.csv", mime="text/csv")

if auto_refresh:
    import time
    time.sleep(10)
    st.rerun()