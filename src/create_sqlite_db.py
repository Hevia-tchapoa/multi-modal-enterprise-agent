"""
Creates a SQLite database containing structured BNP Paribas financial data,
extracted from key figures in the 2025 URD report.

These data allow the agent to answer numeric questions through the
execute_sql tool (Tool 1, Phase 2).
"""

import sqlite3
import os

DB_PATH = "data/finances.db"


def create_database():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"Old database removed: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ----------------------------------------------------------------
    # Table 1: annual group financial results
    # ----------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE annual_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            year INTEGER NOT NULL,
            produit_net_bancaire_meur REAL,    -- Produit Net Bancaire (M€)
            resultat_brut_exploitation_meur REAL,
            resultat_net_part_groupe_meur REAL,
            benefice_net_par_action_eur REAL,
            rentabilite_fonds_propres_pct REAL
        )
    """)

    annual_results = [
        # company,        year, PNB,    RBE,    RN,     BNPA, ROTE
        ("BNP Paribas", 2025, 51223, 19849, 12225, 10.29, 11.6),
        ("BNP Paribas", 2024, 48831, 18638, 11688, 9.57, 10.9),
        ("BNP Paribas", 2023, 45874, 14918, 10975, 8.58, 10.7),
    ]

    cursor.executemany("""
        INSERT INTO annual_results
            (company_name, year, produit_net_bancaire_meur,
             resultat_brut_exploitation_meur, resultat_net_part_groupe_meur,
             benefice_net_par_action_eur, rentabilite_fonds_propres_pct)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, annual_results)

    # ----------------------------------------------------------------
    # Table 2: market capitalization
    # ----------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE market_capitalization (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            date TEXT NOT NULL,            -- format YYYY-MM-DD
            market_cap_md_eur REAL         -- capitalisation en milliards d'euros
        )
    """)

    market_cap = [
        ("BNP Paribas", "2025-12-31", 90.2),
        ("BNP Paribas", "2024-12-31", 67.0),
        ("BNP Paribas", "2023-12-31", 71.8),
    ]

    cursor.executemany("""
        INSERT INTO market_capitalization (company_name, date, market_cap_md_eur)
        VALUES (?, ?, ?)
    """, market_cap)

    # ----------------------------------------------------------------
    # Table 3: revenue by business line (2025)
    # ----------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE revenue_by_division (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            year INTEGER NOT NULL,
            division TEXT NOT NULL,        -- CIB, CPBS, IPS
            revenue_share_pct REAL,         -- part en % des revenus des pôles
            revenue_meur REAL               -- estimation en M€ (PNB * part)
        )
    """)

    # Total 2025 revenue by business line = 51.2 billion euros (as per the report)
    total_2025 = 51200  # en M€
    revenue_by_division = [
        ("BNP Paribas", 2025, "CIB", 36.0, round(total_2025 * 0.36, 1)),
        ("BNP Paribas", 2025, "CPBS", 51.0, round(total_2025 * 0.51, 1)),
        ("BNP Paribas", 2025, "IPS", 13.0, round(total_2025 * 0.13, 1)),
    ]

    cursor.executemany("""
        INSERT INTO revenue_by_division
            (company_name, year, division, revenue_share_pct, revenue_meur)
        VALUES (?, ?, ?, ?, ?)
    """, revenue_by_division)

    # ----------------------------------------------------------------
    # Table 4: credit ratings (agency ratings)
    # ----------------------------------------------------------------
    cursor.execute("""
        CREATE TABLE credit_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            agency TEXT NOT NULL,
            long_term_rating TEXT,
            short_term_rating TEXT,
            outlook TEXT,
            review_date TEXT
        )
    """)

    credit_ratings = [
        ("BNP Paribas", "Standard & Poor's", "A+", "A-1", "Stable", "2025-12-08"),
        ("BNP Paribas", "Fitch", "AA-", "F1+", "Stable", "2025-06-04"),
        ("BNP Paribas", "Moody's", "A1", "Prime-1", "Stable", "2025-11-17"),
        ("BNP Paribas", "DBRS", "AA (low)", "R-1 (middle)", "Stable", "2025-06-17"),
    ]

    cursor.executemany("""
        INSERT INTO credit_ratings
            (company_name, agency, long_term_rating, short_term_rating, outlook, review_date)
        VALUES (?, ?, ?, ?, ?, ?)
    """, credit_ratings)

    conn.commit()
    conn.close()

    print(f"\n✅ SQLite database created: {DB_PATH}")
    print("Tables created: annual_results, market_capitalization, revenue_by_division, credit_ratings")


def preview_database():
    """Displays a preview of the data for verification."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for table in ["annual_results", "market_capitalization", "revenue_by_division", "credit_ratings"]:
        print(f"\n--- {table} ---")
        cursor.execute(f"SELECT * FROM {table}")
        for row in cursor.fetchall():
            print(row)

    conn.close()


if __name__ == "__main__":
    create_database()
    preview_database()