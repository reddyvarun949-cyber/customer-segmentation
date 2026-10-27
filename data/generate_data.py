"""Generate the synthetic online-grocery dataset used in this project.

Run from the project root:  python data/generate_data.py
It writes two files (the seed is fixed, so everyone gets the same data):
    data/orders.csv      one row per order (about 30,000 orders in calendar year 2025)
    data/customers.csv   one row per registered customer (about 2,540 customers)

How the data is made
--------------------
Every customer is secretly given a shopping "style" (for example a frequent big-basket shopper, or a deal seeker
who mostly orders with coupons). The style decides roughly how often they order, how much they spend, how often
they use coupons, whether they prefer the app or the website and how many grocery categories they buy from.
Each customer also gets personal random variation, so the styles overlap like real people do.

The style is NOT saved in the CSV files. In real life nobody hands you the "true" segments, and clustering is
about discovering useful groups, not recovering a hidden answer.

A few rows are made messy on purpose so the notebook can show how to clean them:
duplicated order rows, missing order values, refunds recorded as zero/negative values, inconsistent spelling of
the channel column, missing ages, and some registered customers who never placed an order.
"""
import os

import numpy as np
import pandas as pd

SEED = 42
N_ACTIVE = 2500          # customers with at least one order
N_NEVER_ORDERED = 40     # signed up but never ordered (they appear only in customers.csv)
YEAR_START = pd.Timestamp("2025-01-01")
DAYS_IN_YEAR = 365

CATEGORIES = ["Fruits & Vegetables", "Dairy & Bakery", "Staples", "Snacks & Beverages",
              "Household", "Personal Care", "Meat & Seafood"]
CITIES = ["Bengaluru", "Mumbai", "Delhi", "Hyderabad", "Pune", "Chennai"]

# Hidden shopping styles (share of customers and typical behaviour). Numbers are invented but plausible.
STYLES = {
    #               share  orders/yr  basket(Rs)  coupon  app    categories  active_until_day
    "frequent_big":  (0.12, 32,        1700,       0.10,   0.85,  7,          365),
    "regular":       (0.25, 18,        850,        0.15,   0.60,  5,          365),
    "deal_seeker":   (0.20, 11,        480,        0.70,   0.70,  3,          365),
    "occasional":    (0.25, 4,         1100,       0.15,   0.20,  3,          365),
    "lapsed":        (0.18, 4,         750,        0.30,   0.45,  3,          150),
}


def make_customers(rng):
    n = N_ACTIVE + N_NEVER_ORDERED
    names = list(STYLES)
    shares = np.array([STYLES[s][0] for s in names])
    style = rng.choice(names, size=N_ACTIVE, p=shares / shares.sum())
    customers = pd.DataFrame({
        "customer_id": [f"C{i:05d}" for i in range(1, n + 1)],
        "age": rng.normal(36, 11, n).clip(18, 75).round(0),
        "city": rng.choice(CITIES, size=n, p=[0.24, 0.2, 0.2, 0.14, 0.12, 0.1]),
        # sign-up somewhere between 2021 and the end of 2025 (fixed below so it is before the first order)
        "signup_date": YEAR_START + pd.to_timedelta(rng.integers(-4 * 365, 330, n), unit="D"),
    })
    return customers, style


def make_orders(rng, customers, style):
    rows = []
    order_no = 100000
    for i, s in enumerate(style):
        _, n_orders, basket, coupon_p, app_p, n_cats, active_until = STYLES[s]
        cid = customers.at[i, "customer_id"]
        # personal variation around the style
        k = max(1, rng.poisson(n_orders * rng.uniform(0.6, 1.4)))
        my_basket = basket * rng.lognormal(0, 0.25)
        my_coupon = np.clip(rng.beta(2, 2) * 0.4 + coupon_p - 0.2, 0, 1)
        my_app = np.clip(rng.beta(2, 2) * 0.4 + app_p - 0.2, 0, 1)
        my_cats = rng.choice(CATEGORIES, size=min(7, max(1, n_cats + rng.integers(-1, 2))), replace=False)
        # when are they active? lapsed customers stop early, others shop all year
        last_day = active_until if s != "lapsed" else rng.integers(60, active_until + 1)
        first_day = rng.integers(0, 60) if s != "occasional" else 0
        days = np.sort(rng.integers(first_day, last_day, k))
        for d in days:
            value = my_basket * rng.lognormal(0, 0.35)
            rows.append({
                "order_id": f"O{order_no}",
                "customer_id": cid,
                "order_date": (YEAR_START + pd.Timedelta(days=int(d))).strftime("%Y-%m-%d"),
                "order_value": round(float(value), 2),
                "items": int(max(1, rng.poisson(value / 110))),
                "category": rng.choice(my_cats),
                "used_coupon": int(rng.random() < my_coupon),
                "channel": "app" if rng.random() < my_app else "web",
            })
            order_no += 1
    orders = pd.DataFrame(rows)
    # orders are numbered in time order, like a real system
    orders = orders.sort_values(["order_date", "customer_id"]).reset_index(drop=True)
    orders["order_id"] = [f"O{100000 + i}" for i in range(len(orders))]
    return orders


def add_mess(rng, orders, customers):
    n = len(orders)
    # 1. missing order values (logging glitch)
    orders.loc[rng.choice(n, 60, replace=False), "order_value"] = np.nan
    # 2. refunds / cancelled orders recorded with value 0 or negative
    idx = rng.choice(n, 45, replace=False)
    orders.loc[idx, "order_value"] = -orders.loc[idx, "order_value"].abs().fillna(300).round(2)
    orders.loc[idx[:15], "order_value"] = 0.0
    # 3. inconsistent spelling in the channel column
    idx = rng.choice(n, 400, replace=False)
    orders.loc[idx, "channel"] = rng.choice(["App", "APP", "Web", "WEB", " web"], size=len(idx))
    # 4. the same order exported twice
    dupes = orders.sample(150, random_state=SEED)
    orders = pd.concat([orders, dupes], ignore_index=True).sample(frac=1, random_state=SEED).reset_index(drop=True)
    # 5. missing ages in the customers table
    customers.loc[rng.choice(len(customers), 120, replace=False), "age"] = np.nan
    return orders, customers


def make_dataset(seed=SEED):
    rng = np.random.default_rng(seed)
    customers, style = make_customers(rng)
    orders = make_orders(rng, customers, style)
    # a customer must have signed up on or before their first order
    first = pd.to_datetime(orders.groupby("customer_id")["order_date"].min())
    signup = customers.set_index("customer_id")["signup_date"]
    fixed = signup.where(~signup.index.isin(first.index) | (signup <= first.reindex(signup.index)),
                         first.reindex(signup.index) - pd.Timedelta(days=1))
    customers["signup_date"] = fixed.to_numpy()
    customers["signup_date"] = pd.to_datetime(customers["signup_date"]).dt.strftime("%Y-%m-%d")
    orders, customers = add_mess(rng, orders, customers)
    return orders, customers


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    orders, customers = make_dataset()
    orders.to_csv(os.path.join(here, "orders.csv"), index=False)
    customers.to_csv(os.path.join(here, "customers.csv"), index=False)
    print(f"Wrote {len(orders)} order rows for {orders['customer_id'].nunique()} customers to data/orders.csv")
    print(f"Wrote {len(customers)} customers to data/customers.csv")
