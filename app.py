"""
Tracker des ventes du jour - Spa le Finlandais
Importe un rapport Sales-Accrual (Zenoti) et affiche, pour la journée,
le nombre de massages vendus et de cartes-cadeaux fidélité par employé.
"""

import io
import re
import pandas as pd
import streamlit as st

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
# Montants (taxes incluses) reconnus comme cartes-cadeaux FIDÉLITÉ.
# Les autres cartes-cadeaux (montants ronds, etc.) sont ignorées.
LOYALTY_AMOUNTS = {52.08, 52.09, 63.58, 63.59, 140.56, 152.06, 163.56, 170.46, 181.96}

st.set_page_config(page_title="Ventes du jour — Spa le Finlandais",
                   page_icon="💆", layout="wide")


# ----------------------------------------------------------------------
# Parsing du rapport Sales-Accrual
# ----------------------------------------------------------------------
def find_header_row(raw: pd.DataFrame) -> int:
    """Trouve la ligne d'en-tête contenant 'Sold By'."""
    for i in range(min(20, len(raw))):
        if raw.iloc[i].astype(str).str.strip().eq("Sold By").any():
            return i
    raise ValueError("En-tête « Sold By » introuvable — est-ce bien un rapport Sales-Accrual ?")


def extract_report_date(raw: pd.DataFrame):
    """Tente de lire la date du rapport dans les lignes d'en-tête (From : ...)."""
    months = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
              "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
    for i in range(min(20, len(raw))):
        line = " ".join(str(x) for x in raw.iloc[i].tolist() if pd.notna(x))
        m = re.search(r"From\s*:?\s*(\d{1,2})\s+(\w{3})\w*\s+(\d{4})", line, re.I)
        if m:
            mo = months.get(m.group(2)[:3].lower())
            if mo:
                return f"{int(m.group(3)):04d}-{mo:02d}-{int(m.group(1)):02d}"
    return None


def parse_sales_accrual(file_bytes: bytes):
    """Retourne (DataFrame par employé, totaux, date_du_rapport)."""
    raw = pd.read_excel(io.BytesIO(file_bytes), header=None)
    hdr = find_header_row(raw)
    report_date = extract_report_date(raw)

    df = pd.read_excel(io.BytesIO(file_bytes), header=hdr)
    df.columns = [str(c).strip() for c in df.columns]

    # Colonne du montant taxes incluses (le nom varie légèrement selon l'export)
    inc_col = next((c for c in df.columns if c.replace(" ", "").lower().startswith("sales(inc")), None)
    if inc_col is None:
        raise ValueError("Colonne « Sales(Inc. Tax) » introuvable.")

    df["Employee"] = df["Sold By"].ffill()
    tx = df[df["Item Type"].notna()].copy()

    data = {}
    for _, r in tx.iterrows():
        name = r["Employee"]
        if pd.isna(name) or str(name).strip() in ("", "Total:"):
            continue
        name = str(name).strip()
        rec = data.setdefault(name, {"Massages": 0, "Cartes fidélité": 0})

        item_type = str(r["Item Type"]).strip()
        if item_type == "Service":
            qty = r.get("Qty")
            rec["Massages"] += int(qty) if pd.notna(qty) else 0
        elif item_type == "Gift card":
            amt = r.get(inc_col)
            if pd.notna(amt) and round(float(amt), 2) in LOYALTY_AMOUNTS:
                rec["Cartes fidélité"] += 1

    result = pd.DataFrame(
        [{"Employé": n, **v} for n, v in data.items()]
    ).sort_values("Employé").reset_index(drop=True)

    totals = {
        "Massages": int(result["Massages"].sum()) if not result.empty else 0,
        "Cartes fidélité": int(result["Cartes fidélité"].sum()) if not result.empty else 0,
    }
    return result, totals, report_date


# ----------------------------------------------------------------------
# Interface
# ----------------------------------------------------------------------
st.title("💆 Ventes du jour — Spa le Finlandais")
st.caption("Importer le rapport Sales-Accrual de la journée pour voir les ventes par employé.")

uploaded = st.file_uploader(
    "Rapport Sales-Accrual (.xlsx ou .csv)",
    type=["xlsx", "xls", "csv"],
    help="Exporté depuis Zenoti."
)

if uploaded is None:
    st.info("⬆️ Glissez le rapport de la journée pour commencer.")
    st.stop()

try:
    table, totals, report_date = parse_sales_accrual(uploaded.getvalue())
except Exception as e:
    st.error(f"⚠️ Impossible de lire le fichier : {e}")
    st.stop()

if report_date:
    st.subheader(f"Journée du {report_date}")

# Cartes de totaux
c1, c2, c3 = st.columns(3)
c1.metric("Massages vendus", totals["Massages"])
c2.metric("Cartes fidélité", totals["Cartes fidélité"])
c3.metric("Employés actifs", len(table))

st.divider()

if table.empty:
    st.warning("Aucune vente trouvée dans ce rapport.")
    st.stop()

# Tableau avec ligne de total
display = table.copy()
total_row = pd.DataFrame([{
    "Employé": "TOTAL",
    "Massages": totals["Massages"],
    "Cartes fidélité": totals["Cartes fidélité"],
}])
display = pd.concat([display, total_row], ignore_index=True)

st.dataframe(
    display,
    use_container_width=True,
    hide_index=True,
    column_config={
        "Employé": st.column_config.TextColumn("Employé", width="large"),
        "Massages": st.column_config.NumberColumn("Massages vendus", format="%d"),
        "Cartes fidélité": st.column_config.NumberColumn("Cartes fidélité", format="%d"),
    },
)

# Export CSV de la journée
csv = display.to_csv(index=False).encode("utf-8-sig")
fname = f"ventes_{report_date}.csv" if report_date else "ventes_du_jour.csv"
st.download_button("⬇️ Télécharger en CSV", csv, file_name=fname, mime="text/csv")

with st.expander("ℹ️ Comment les cartes fidélité sont comptées"):
    st.write(
        "Seules les cartes-cadeaux dont le montant (taxes incluses) correspond à "
        "un montant fidélité reconnu sont comptées : "
        "52.08 / 52.09 · 63.58 / 63.59 · 140.56 · 152.06 · 163.56 · 170.46 · 181.96. "
        "Les autres cartes-cadeaux (montants ronds, autres valeurs) sont ignorées. "
        "Les massages correspondent aux lignes de type « Service »."
    )
