import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


# ---------------------------------------------------------
# Load environment variables from .env
# ---------------------------------------------------------

load_dotenv()


# ---------------------------------------------------------
# Read database configuration
# ---------------------------------------------------------

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME", "bank_loan_risk")


# ---------------------------------------------------------
# Validate required configuration
# ---------------------------------------------------------

if not DB_USER:
    raise ValueError(
        "DB_USER is not configured. "
        "Please add DB_USER to the .env file."
    )

if DB_PASSWORD is None:
    raise ValueError(
        "DB_PASSWORD is not configured. "
        "Please add DB_PASSWORD to the .env file."
    )


# ---------------------------------------------------------
# Create database URL
# ---------------------------------------------------------

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)


# ---------------------------------------------------------
# Create SQLAlchemy Engine
# ---------------------------------------------------------

engine: Engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=3600
)


# ---------------------------------------------------------
# Reusable function to obtain the engine
# ---------------------------------------------------------

def get_engine() -> Engine:
    """
    Return the application's SQLAlchemy database engine.

    Other ETL modules should use this function instead of
    creating their own database connections.
    """
    return engine


# ---------------------------------------------------------
# Test database connection
# ---------------------------------------------------------

def test_connection() -> bool:
    """
    Test whether the application can connect to MySQL.

    Returns:
        True if connection succeeds.
        False if connection fails.
    """

    try:
        with engine.connect() as connection:

            result = connection.execute(
                text("SELECT DATABASE();")
            )

            database_name = result.scalar()

            print("Database connection successful.")
            print(f"Connected database: {database_name}")

            return True

    except Exception as exc:

        print("Database connection failed.")
        print(f"Error: {exc}")

        return False
#python -m db.connection     --> to test the connection

# ---------------------------------------------------------
# Run connection test when executed directly
# ---------------------------------------------------------

if __name__ == "__main__":
    test_connection()