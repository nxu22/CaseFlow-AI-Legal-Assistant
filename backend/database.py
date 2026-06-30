"""
SQLAlchemy database connection and session management.

Design notes:
- create_engine with pool_pre_ping=True: tests connections before use,
  prevents stale connection errors after idle periods
  (relevant on AWS RDS where connections may be dropped).
- SessionLocal is a factory; we create a fresh session per request via
  the get_db() FastAPI dependency, then close it cleanly.
- Base is the declarative base all ORM models inherit from.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

# Use APP_DATABASE_URL (non-superuser, RLS applies) when available.
# Falls back to DATABASE_URL so the app still starts before the RLS migration runs.
_app_db_url = settings.APP_DATABASE_URL or settings.DATABASE_URL

engine = create_engine(
    _app_db_url,
    pool_pre_ping=True,
    echo=settings.ENVIRONMENT == "development",
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


@event.listens_for(engine, "checkout")
def _reset_tenant_on_checkout(dbapi_connection, connection_record, connection_proxy):
    # Ensure every connection leaving the pool starts with no tenant context.
    # Without this, SET LOCAL inside a previous transaction leaves the GUC as ''
    # (empty string) rather than NULL after the transaction ends, which causes
    # the RLS policy's ::uuid cast to fail on the next request using that connection.
    with dbapi_connection.cursor() as cur:
        cur.execute("RESET app.current_tenant")


def get_db():
    """
    FastAPI dependency that provides a database session per request.
    Usage in endpoints:
        def endpoint(db: Session = Depends(get_db)): ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
