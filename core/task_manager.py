from db.database import insert, query_all


def list_tasks():
    return query_all('SELECT * FROM tasks ORDER BY id DESC')
