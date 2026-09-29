"""Run every query in sql/ against the warehouse and write outputs/*.csv.

Those CSVs are the Tableau extracts. Tableau connects to the folder, not to
DuckDB, so the dashboard has no live database dependency and the repo stays
reproducible for anyone who clones it.
"""
import pathlib
import sys

import duckdb

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "nfip.duckdb"
SQL = ROOT / "sql"
OUT = ROOT / "outputs"


def main() -> int:
    if not DB.exists():
        raise SystemExit("No warehouse. Run: python src/build_db.py")
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB), read_only=True)

    failures = 0
    for path in sorted(SQL.glob("*.sql")):
        dest = OUT / f"{path.stem}.csv"
        try:
            df = con.execute(path.read_text()).fetchdf()
        except Exception as exc:
            print(f"  FAILED {path.name}: {exc}", file=sys.stderr)
            failures += 1
            continue
        df.to_csv(dest, index=False)
        print(f"  {path.name:<34} -> {dest.name:<34} {len(df):>7,} rows")

    con.close()
    print(f"\nwrote {len(list(OUT.glob('*.csv')))} extracts to outputs/")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
