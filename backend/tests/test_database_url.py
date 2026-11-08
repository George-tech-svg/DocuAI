from sqlalchemy.engine import make_url

from app.core.config import psycopg_database_url


def test_database_url_explicitly_selects_psycopg3():
    normalized = psycopg_database_url(
        'postgresql://user:pass@db.example.test/app?sslmode=require&channel_binding=require'
    )
    parsed = make_url(normalized)

    assert parsed.drivername == 'postgresql+psycopg'
    assert parsed.query['sslmode'] == 'require'
    assert parsed.query['channel_binding'] == 'require'


def test_database_url_keeps_explicit_driver():
    normalized = psycopg_database_url('postgresql+psycopg://user:pass@db.example.test/app')

    assert make_url(normalized).drivername == 'postgresql+psycopg'
