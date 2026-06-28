from db.database import query_all


def list_skills():
    return query_all('SELECT * FROM skills ORDER BY id')
