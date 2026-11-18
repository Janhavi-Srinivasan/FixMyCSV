"""Generates a deliberately messy customer CSV to try the app with."""
import random
import pandas as pd

random.seed(7)
cities = ["Chennai", "Mumbai", "Delhi", "Bengaluru", "Hyderabad"]
variants = {"Chennai": ["chennai", "Chenai", "CHENNAI", " Chennai "], "Mumbai": ["mumbai", "Mumbai ", "MUMBAI"],
            "Delhi": ["delhi", "DELHI", "Delhi."], "Bengaluru": ["bengaluru", "Bangalore"], "Hyderabad": ["hyderabad"]}
rows = []
for i in range(1, 241):
    city = random.choice(cities)
    if random.random() < 0.3:
        city = random.choice(variants[city])
    age = random.randint(19, 70)
    income = round(random.gauss(55000, 14000), 0)
    spend = round(max(income * random.uniform(0.2, 0.6), 100), 2)
    d = f"20{random.randint(20, 25)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}"
    rows.append({"Customer ID": 1000 + i, "Full Name": f"Customer {i}", "Age": age, "City": city,
                 "Annual Income": f"${income:,.0f}", "Monthly Spend": spend, "Signup Date": d,
                 "Newsletter": random.choice(["yes", "no", "Yes", "NO"])})
df = pd.DataFrame(rows)
for _ in range(12):  # missing values / placeholders
    df.loc[random.randrange(len(df)), "Age"] = None
for _ in range(10):
    df.loc[random.randrange(len(df)), "City"] = random.choice(["N/A", "null", "-", ""])
for _ in range(8):
    df.loc[random.randrange(len(df)), "Monthly Spend"] = None
df.loc[5, "Age"] = 240                       # outliers
df.loc[17, "Age"] = -3
df.loc[30, "Monthly Spend"] = 98000.0
df.loc[41, "Annual Income"] = "not provided"  # invalid number
df.loc[50, "Signup Date"] = "2023-13-45"     # invalid dates
df.loc[51, "Signup Date"] = "31/02/2022"
df.loc[60, "Signup Date"] = "March 3, 2021"
df.loc[70, "Full Name"] = "  Customer 70  "
df = pd.concat([df, df.sample(9, random_state=1)], ignore_index=True)  # duplicates
df.to_csv("sample_data/messy_customers.csv", index=False)
print(df.shape)
