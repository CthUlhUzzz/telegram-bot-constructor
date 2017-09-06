from telegram_bot_constructor import set_redis_connection, get_redis_connection
from redis import Redis
from telegram_bot_constructor.operators_server import Operator, Message
import time
import uuid
import random

set_redis_connection(Redis(host='127.0.0.1', port=6379, db=9))
redis_ = get_redis_connection()
redis_.flushdb()


def add_incoming_message(conversation, text):
    message = Message.create(0, text)
    redis_.zadd('conversations:%d:messages' % conversation.id, message.id, time.time())


o = Operator.create('Test')

for _ in range(random.randint(0, 10)):
    c = o.new_conversation()
    for __ in range(random.randint(0, 10)):
        direction = random.choice((0, 1))
        if direction == 0:
            add_incoming_message(c, str(uuid.uuid4()))
        elif direction == 1:
            c.send_message(str(uuid.uuid4()))
print(Operator.list())
# print(c.messages)
# print(c.started_at)
# c.start()
# print(o.conversations)
# print(c.messages)
# print(c.started_at)
# c.send_message('Test')

# c.send_message('Test2')
# c.send_message('Test3')
# print(o.conversations)
# print(c.messages)
# print(c.started_at)

# print(c.messages)
# Operator.delete(o)
# Message.delete(Message(0))
# Operator.delete(o)
