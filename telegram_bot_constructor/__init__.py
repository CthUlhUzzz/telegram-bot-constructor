redis_connection = None


def get_redis_connection():
    global redis_connection
    return redis_connection


def set_redis_connection(connection):
    global redis_connection
    redis_connection = connection
