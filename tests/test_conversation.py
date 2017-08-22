from telegram_bot_constructor import set_redis_connection, get_redis_connection
from redis import Redis
from telegram_bot_constructor.operators_server import Operator

set_redis_connection(Redis(host='127.0.0.1', port=6379, db=9))
get_redis_connection().flushdb()
o = Operator.create('Test')
c = o.new_conversation()
print(o.conversations)
print(c.messages)
print(c.started_at)
c.start()
print(o.conversations)
print(c.messages)
print(c.started_at)
c.send_message('Test')
print(o.conversations)
print(c.messages)
print(c.started_at)

# print(c.messages)
# Operator.delete(o)
# Message.delete(Message(0))
# Operator.delete(o)
