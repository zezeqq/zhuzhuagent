from db.database import query_all


def list_workflows():
    return query_all('SELECT * FROM workflows ORDER BY id')
