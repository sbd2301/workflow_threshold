"""
daily_report.py
---------------
1. Downloads SwissGrid AE-Preis data (replace URL / parsing with your real source).
2. Creates a plot with a threshold line.
3. Sends an e-mail whose subject and body reflect whether the threshold was breached.
"""

import os
import base64
import datetime
import requests
import pandas as pd
import matplotlib
matplotlib.use("Agg")          # headless – no display needed
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import resend

# ── Configuration ────────────────────────────────────────────────────────────

THRESHOLD = 150.0              # CHF/MWh  ← adjust to your needs
PLOT_FILE = "ae_preis.png"

# Example: SwissGrid publishes Regelenergie data as Excel files.
# Replace DATA_URL and the parsing block below with your real source.
DATA_URL = (
    "https://www.swissgrid.ch/dam/dataimport/energy-statistic/"
    "EnergieUebersichtCH-2024.xlsx"
)

# ── 1. Download ───────────────────────────────────────────────────────────────

print("Downloading data …")
response = requests.get(DATA_URL, timeout=60)
response.raise_for_status()

with open("raw_data.xlsx", "wb") as f:
    f.write(response.content)

# ── 2. Parse ─────────────────────────────────────────────────────────────────
# Adapt sheet name / column names to the file you actually use.

df = pd.read_excel("raw_data.xlsx", sheet_name=0, header=0)

# --- MOCK fallback so the workflow works end-to-end even with a wrong URL ---
# Remove this block once you point DATA_URL at the real file.
if df.empty or "Datum" not in df.columns:
    print("Using synthetic demo data (replace DATA_URL with the real source).")
    rng = pd.date_range(end=datetime.date.today(), periods=30, freq="D")
    import random, math
    df = pd.DataFrame({
        "Datum": rng,
        "AE_Preis": [
            120 + 60 * math.sin(i / 5) + random.uniform(-10, 10)
            for i in range(30)
        ],
    })

df["Datum"] = pd.to_datetime(df["Datum"])
df = df.sort_values("Datum").tail(30)          # last 30 days

latest_value = df["AE_Preis"].iloc[-1]
latest_date  = df["Datum"].iloc[-1].strftime("%Y-%m-%d")

# ── 3. Plot ───────────────────────────────────────────────────────────────────

fig, ax = plt.subplots(figsize=(10, 4))

ax.plot(df["Datum"], df["AE_Preis"],
        color="#1f77b4", linewidth=1.8, label="AE-Preis (CHF/MWh)")

# Threshold line
ax.axhline(THRESHOLD, color="crimson", linewidth=1.4,
           linestyle="--", label=f"Threshold {THRESHOLD} CHF/MWh")

# Colour the area above / below the threshold
ax.fill_between(
    df["Datum"], df["AE_Preis"], THRESHOLD,
    where=(df["AE_Preis"] >= THRESHOLD),
    interpolate=True, alpha=0.20, color="crimson", label="Above threshold"
)
ax.fill_between(
    df["Datum"], df["AE_Preis"], THRESHOLD,
    where=(df["AE_Preis"] < THRESHOLD),
    interpolate=True, alpha=0.15, color="#1f77b4", label="Below threshold"
)

# Mark the latest point
marker_color = "crimson" if latest_value >= THRESHOLD else "#1f77b4"
ax.scatter([df["Datum"].iloc[-1]], [latest_value],
           color=marker_color, zorder=5, s=60)
ax.annotate(
    f"{latest_value:.1f}",
    xy=(df["Datum"].iloc[-1], latest_value),
    xytext=(8, 6), textcoords="offset points",
    fontsize=9, color=marker_color
)

ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
fig.autofmt_xdate()

ax.set_title("SwissGrid AE-Preis – last 30 days", fontsize=13)
ax.set_ylabel("CHF / MWh")
ax.legend(fontsize=8)
ax.grid(axis="y", linestyle=":", alpha=0.5)

plt.tight_layout()
plt.savefig(PLOT_FILE, dpi=150)
plt.close()
print(f"Plot saved to {PLOT_FILE}.")

# ── 4. Build conditional e-mail content ───────────────────────────────────────

threshold_breached = latest_value >= THRESHOLD

if threshold_breached:
    subject = f"🔴 SwissGrid AE-Preis – THRESHOLD REACHED ({latest_value:.1f} CHF/MWh)"
    status_badge = (
        f'<span style="color:crimson;font-weight:bold;">'
        f'⚠️ THRESHOLD REACHED – {latest_value:.1f} CHF/MWh '
        f'(≥ {THRESHOLD} CHF/MWh)</span>'
    )
    status_text = (
        f"⚠️  The latest AE-Preis ({latest_value:.1f} CHF/MWh) "
        f"is AT OR ABOVE the threshold of {THRESHOLD} CHF/MWh."
    )
else:
    subject = f"🟢 SwissGrid AE-Preis – threshold not reached ({latest_value:.1f} CHF/MWh)"
    status_badge = (
        f'<span style="color:green;font-weight:bold;">'
        f'✅ Threshold not reached – {latest_value:.1f} CHF/MWh '
        f'(< {THRESHOLD} CHF/MWh)</span>'
    )
    status_text = (
        f"✅  The latest AE-Preis ({latest_value:.1f} CHF/MWh) "
        f"is BELOW the threshold of {THRESHOLD} CHF/MWh."
    )

print(status_text)

# ── 5. Send e-mail ────────────────────────────────────────────────────────────

resend.api_key = os.environ["RESEND_API_KEY"]

with open(PLOT_FILE, "rb") as f:
    img_data = base64.b64encode(f.read()).decode("utf-8")

html_body = f"""
<h2>SwissGrid AE-Preis – Daily Update ({latest_date})</h2>
<p style="font-size:1.05em;">{status_badge}</p>
<p>Threshold configured at <strong>{THRESHOLD} CHF/MWh</strong>.</p>
<img src="data:image/png;base64,{img_data}" style="max-width:100%;border:1px solid #ddd;" />
<p style="color:#888;font-size:0.85em;">
  Generated automatically by GitHub Actions · {datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}
</p>
"""

resend.Emails.send({
    "from": os.environ["MAIL_FROM"],
    "to":   os.environ["MAIL_TO"],
    "subject": subject,
    "html": html_body,
    "attachments": [{"filename": PLOT_FILE, "content": img_data}],
})

print("E-mail sent.")
