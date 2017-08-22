from redis import Redis

from telegram_bot_constructor import set_redis_connection
from telegram_bot_constructor.operator_client import OperatorInterfaceDispatcher, ConversationStopped
from telegram_bot_constructor.operators_server import Operator
from telegram_bot_constructor.operators_server import OPERATOR_ACCESS_DENIED, \
    OPERATOR_ALREADY_CONNECTED, OPERATOR_STATUSES, OPERATOR_ACCESS_GRANTED

set_redis_connection(Redis(host='127.0.0.1', port=6379, db=9))
dispatcher = OperatorInterfaceDispatcher()
interface = dispatcher.get_interface(Operator(0).token)

while True:
    dispatcher.update()

    if interface.authentication == OPERATOR_ACCESS_GRANTED:
        print('Authenticated %s' % interface.operator_token)
        break
    elif interface.authentication == OPERATOR_ACCESS_DENIED:
        print('Access denied %s' % interface.operator_token)
        break
    elif interface.authentication == OPERATOR_ALREADY_CONNECTED:
        print('Already connected %s' % interface.operator_token)
        break

while True:
    dispatcher.update()
    if interface.conversation_started:
        print('Conversation started')
        break

while True:
    dispatcher.update()
    try:
        messages = interface.receive_messages()
        if len(messages) != 0:
            for m in messages:
                print('<- %s' % m)
                interface.send_message('Response')
                print('-> Response')
    except ConversationStopped:
        print('Conversation stopped')
        dispatcher.release_interface(interface)
        break
