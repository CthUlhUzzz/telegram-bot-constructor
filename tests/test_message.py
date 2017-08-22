from _old.messaging import Message
from telegram_bot_constructor import set_redis_connection, get_redis_connection
from redis import Redis

set_redis_connection(Redis(host='127.0.0.1', port=6379, db=9))
get_redis_connection().flushdb()
m = Message.create(1, 'Hello')
print(m.text)
print(m.direction)
print(m.time)
