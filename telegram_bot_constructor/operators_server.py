import json
import random
import time
from collections import OrderedDict
from datetime import datetime
from logging import getLogger

from telegram_bot_vm.actions import BaseAction

from . import get_redis_connection
from .helpers import random_token, StoredObject

OPERATOR_ALREADY_CONNECTED = 0
OPERATOR_ACCESS_DENIED = 1
OPERATOR_ACCESS_GRANTED = 2

OPERATOR_STATUSES = (OPERATOR_ALREADY_CONNECTED, OPERATOR_ACCESS_DENIED, OPERATOR_ACCESS_GRANTED)

logger = getLogger('Operators server')


class Message(StoredObject):
    MNEMONIC = 'message'

    def init(self, direction, text):
        self.direction = direction
        self.text = text

    def clean_up(self):
        self.redis.delete('messages:%d:direction' % self.id)
        self.redis.delete('messages:%d:text' % self.id)

    @property
    def direction(self):
        return int(self.redis.get('messages:%d:direction' % self.id))

    @direction.setter
    def direction(self, direction):
        self.redis.set('messages:%d:direction' % self.id, direction)

    @property
    def text(self):
        return self.redis.get('messages:%d:text' % self.id).decode()

    @text.setter
    def text(self, text):
        self.redis.set('messages:%d:text' % self.id, text)


class ConversationStopped(Exception):
    pass


def conversation_check(func):
    def wrapped(self, *args, **kwargs):
        if not self.stopped:
            return func(self, *args, **kwargs)
        else:
            raise ConversationStopped

    return wrapped


class Conversation(StoredObject):
    MNEMONIC = 'conversation'

    def __init__(self, id_, redis_=None):
        super().__init__(id_, redis_)
        self.stopped = False
        self.pubsub = self.redis.pubsub(ignore_subscribe_messages=True)
        self.incoming_messages = []
        self.operator = None

    def init(self, operator):
        self.operator = operator
        self.redis.publish('conversation_started', json.dumps(operator.token))
        self.redis.rpush('operators:%s:conversations' % operator.id, self.id)
        logger.info('Conversation started with operator %s' % operator.token)

    def clean_up(self):
        for message in self.messages.values():
            message.delete()
        self.redis.delete('conversations:%d:messages' % self.id)

    @conversation_check
    def send_message(self, text):
        message = Message.create(1, text)
        self.redis.zadd('conversations:%d:messages' % self.id, message.id, time.time())
        self.redis.publish('message_to_operator', json.dumps((self.operator.token, text)))
        logger.info('Message %s received from user %s' % (text, self.operator.token))

    @conversation_check
    def receive_messages(self):
        for text in self.incoming_messages:
            message = Message.create(0, text)
            self.redis.zadd('conversations:%d:messages' % self.id, message.id, time.time())
            logger.info('Message %s received from operator %s' % (text, self.operator.token))
        incoming_messages = self.incoming_messages
        self.incoming_messages = []
        return incoming_messages

    @conversation_check
    def stop(self):
        self.redis.publish('conversation_stopped_by_user', json.dumps(self.operator.token))
        self.stopped = True
        self.incoming_messages = []

    @property
    def messages(self):
        """ return messages OrderedDict """
        messages = OrderedDict()
        for message, time_ in self.redis.zrange('conversations:%d:messages' % self.id, 0,-1,withscores=True):
            messages[datetime.fromtimestamp(float(time_))] = Message(int(message))
        return messages


class OperatorDialogAction(BaseAction):
    def __init__(self, start_message='Operator connected. Type /enough for stop',
                 stop_message='Operator disconnected',
                 fail_message='No free operators'):
        self.start_message = start_message
        self.stop_message = stop_message
        self.fail_message = fail_message

    def exec(self, vm_context):
        vm_context.operators_dispatcher.update()
        conversation = getattr(vm_context, 'conversation', None)
        if conversation is not None:
            if not conversation.stopped:
                if vm_context.input is not None:
                    if vm_context.input != '/enough':
                        conversation.send_message(vm_context.input)
                        vm_context.input = None
                    else:
                        conversation.stop()
                        logger.info('Conversation stopped by user %s' % conversation.operator.token)
                        vm_context.input = None
                        vm_context.position += 1
                        del vm_context.conversation
                        return self.stop_message,
                return vm_context.conversation.receive_messages()
            else:
                vm_context.position += 1
                del vm_context.conversation
                return self.stop_message,
        else:
            conversation = vm_context.operators_dispatcher.get_conversation()
            if conversation is not None:
                vm_context.conversation = conversation
                return self.start_message,
            else:
                vm_context.position += 1
                return self.fail_message,


class Operator(StoredObject):
    MNEMONIC = 'operator'

    def new_conversation(self):
        """ return new Conversation object for operator """
        conversation = Conversation.create(self)
        self.redis.rpush('operator:%d:conversations' % self.id, conversation.id)
        return conversation

    def regenerate_token(self):
        """ Regenerate operator token """
        self.token = random_token()

    @property
    def token(self):
        """ return current token """
        return self.redis.get('operators:%d:token' % self.id).decode()

    @token.setter
    def token(self, token):
        self.redis.set('operators:%d:token' % self.id, token)

    @property
    def name(self):
        return self.redis.get('operators:%d:name' % self.id).decode()

    @name.setter
    def name(self, name):
        self.redis.set('operators:%d:name' % self.id, name)

    @property
    def conversations(self):
        conversations = self.redis.lrange('operator:%d:conversations' % self.id, 0, -1)
        return tuple(Conversation(int(c)) for c in conversations)

    def init(self, name):
        self.name = name
        self.token = random_token()
        self.redis.rpush('operators_list', self.id)

    def clean_up(self):
        for conversation in self.conversations:
            conversation.delete()
        self.redis.delete('operators:%d:conversations' % self.id)
        self.redis.delete('operators:%d:name' % self.id)
        self.redis.delete('operators:%d:token' % self.id)
        self.redis.lrem('operators_list', self.id)

    @classmethod
    def list(cls):
        redis_ = get_redis_connection()
        operators = redis_.lrange('operators_list', 0, -1)
        return tuple(cls(int(o)) for o in operators)


class OperatorsDispatcher:
    def __init__(self, operators):
        self.operators = {o.token: o for o in operators}  # Operator token to operator map
        self.redis = get_redis_connection()
        self.pubsub = self.redis.pubsub(ignore_subscribe_messages=True)
        self.pubsub.subscribe('authentication', 'disconnected', 'conversation_stopped_by_operator', 'message_to_user')
        self.available_operators = {}  # Operator token to available operator map
        self.conversations = {}  # Operator token to conversation map

    def _get_operator(self):
        """ return free operator """
        free_operators = tuple(self.operators[operator_token] for operator_token in self.operators
                               if operator_token in self.available_operators
                               and operator_token not in self.conversations)
        if len(free_operators) != 0:
            return random.choice(free_operators)

    def get_conversation(self):
        """ return conversation with free operator """
        operator = self._get_operator()
        if operator is not None:
            conversation = operator.new_conversation()
            self.conversations[operator.token] = conversation
            return conversation

    def update(self):
        """ Update information about available operators and receive messages """

        for _ in range(25):  # Read all redis queue
            message = self.pubsub.get_message()
            if message is not None:
                if message['type'] == 'message':
                    channel = message['channel'].decode()
                    message = json.loads(message['data'].decode())
                    logger.info('Message received from channel %s: %s' % (channel, message))
                    if channel == 'authentication':
                        operator_token, auth_token = message
                        if operator_token in self.operators:
                            if operator_token in self.available_operators:
                                authenticated = OPERATOR_ALREADY_CONNECTED
                            else:
                                self.available_operators[operator_token] = self.operators.get(operator_token)
                                authenticated = OPERATOR_ACCESS_GRANTED
                        else:
                            authenticated = OPERATOR_ACCESS_DENIED
                        self.redis.publish('authentication_result', json.dumps((auth_token, authenticated)))
                        logger.info('Operator %s authentication status sent: %d' % (operator_token, authenticated))
                    elif channel == 'disconnected':
                        if message in self.available_operators:
                            del self.available_operators[message]
                            logger.info('Operator %s disconnected' % message)
                    elif channel == 'message_to_user':
                        operator_token, text = message
                        if operator_token in self.conversations:
                            self.conversations[operator_token].incoming_messages.append(text)
                    elif channel == 'conversation_stopped_by_operator':
                        if message in self.conversations:
                            self.conversations[message].stopped = True
                            logger.info('Conversation stopped by operator %s' % message)
            # Cleaning up stopped conversations
            for operator_token, conversation in self.conversations.copy().items():
                if operator_token not in self.available_operators:
                    conversation.stopped = True
                if conversation.stopped:
                    del self.conversations[operator_token]
