from db.database import execute, insert, query_all


def set_current_project(project_id:int):
    execute('UPDATE projects SET is_current=0')
    execute('UPDATE projects SET is_current=1 WHERE id=?', (project_id,))
