from contextlib import closing

from database import DatabaseError, connect


def main() -> None:
    try:
        with closing(connect()) as connection:
            version = connection.cursor().execute("SELECT @@VERSION").fetchone()[0]
    except DatabaseError as error:
        print(error)
        return
    print("Veza sa bazom uspješna.")
    print(version.splitlines()[0])


if __name__ == "__main__":
    main()
