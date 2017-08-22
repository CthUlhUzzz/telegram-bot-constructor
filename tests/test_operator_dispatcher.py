from redis import Redis
from telegram_bot_vm.machine import BotVM
import logging

from telegram_bot_constructor import set_redis_connection, get_redis_connection
from telegram_bot_constructor.operators_server import OperatorsDispatcher, Operator, OperatorDialogAction

set_redis_connection(Redis(host='127.0.0.1', port=6379, db=9))
get_redis_connection().flushdb()
logging.basicConfig(level=logging.INFO)

with open('test_token') as t:
    token = t.read()

actions = (OperatorDialogAction(),)

operator = Operator.create('TestOperator')
dispatcher = OperatorsDispatcher((operator,))
BotVM.run(actions, token, add_properties={'operators_dispatcher': dispatcher})
