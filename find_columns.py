import sys
from contextlib import closing

from database import DatabaseError, connect

QUERY = """
SELECT TOP 200 TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE COLUMN_NAME LIKE ?
ORDER BY TABLE_NAME, COLUMN_NAME
"""


def main() -> None:
    if len(sys.argv) != 2:
        print("Upotreba: python find_columns.py dio_naziva_kolone")
        return
    pattern = f"%{sys.argv[1]}%"
    try:
        with closing(connect()) as connection:
            rows = connection.cursor().execute(QUERY, pattern).fetchall()
    except DatabaseError as error:
        print(error)
        return
    if not rows:
        print("Nema rezultata.")
        return
    for schema, table, column, data_type in rows:
        print(f"{schema}.{table}.{column}  ({data_type})")


if __name__ == "__main__":
    main()
