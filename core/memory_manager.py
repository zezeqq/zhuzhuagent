from db.database import insert, query_all


def list_memories():
    return query_all('SELECT * FROM memories ORDER BY id DESC')
