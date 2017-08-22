import json
import random
import time
from collections import OrderedDict
from datetime import datetime
from logging import getLogger

from telegram_bot_vm.actions import BaseAction

from . import get_redis_connection
from .helpers import random_token, redis_iter, ZSET

OPERATOR_ALREADY_CONNECTED = 0
OPERATOR_ACCESS_DENIED = 1
OPERATOR_ACCESS_GRANTED = 2

OPERATOR_STATUSES = (OPERATOR_ALREADY_CONNECTED, OPERATOR_ACCESS_DENIED, OPERATOR_ACCESS_GRANTED)

logger = getLogger('Operators server')


class Message:
    def __init__(self, id_, redis_=None):
        self.redis = redis_ if redis_ is not None else get_redis_connection()
        self.id = id_

    @classmethod
    def create(cls, direction, text):
        redis_ = get_redis_connection()
        last_id = redis_.get('last_message_id')
        last_id = int(last_id) if last_id is not None else 0
        redis_.hmset('messages:%d' % last_id, {'direction': direction,
                                               'text': text})
        redis_.incr('last_message_id')
        return cls(last_id, redis_)

    @classmethod
    def delete(cls, message):
        redis_ = get_redis_connection()
        redis_.delete('messages:%d' % message.id)

    @property
    def direction(self):
        return int(self.redis.hget('messages:%d' % self.id, 'direction'))

    @property
    def text(self):
        return self.redis.hget('messages:%d' % self.id, 'text').decode()

    def __eq__(self, other):
        return self.id == other.id


class ConversationStopped(Exception):
    pass


def conversation_check(func):
    def wrapped(self, *args, **kwargs):
        if not self.stopped:
            return func(self, *args, **kwargs)
        else:
            raise ConversationStopped

    return wrapped


class Conversation:
    def __init__(self, id_, redis_=None):
        self.id = id_
        self.stopped = False
        self.redis = redis_ if redis_ is not None else get_redis_connection()
        self.pubsub = self.redis.pubsub(ignore_subscribe_messages=True)
        self.incoming_messages = []
        self.operator = None

    @classmethod
    def create(cls, operator):
        redis_ = get_redis_connection()
        last_id = redis_.get('last_conversation_id')
        last_id = int(last_id) if last_id is not None else 0
        conversation = cls(last_id, redis_)
        conversation.operator = operator
        redis_.publish('conversation_started', json.dumps(operator.token))
        redis_.zadd('operators:%s:conversations' % operator.id, last_id, time.time())
        redis_.incr('last_conversation_id')
        logger.info('Conversation started with operator %s' % operator.token)
        return conversation

    def delete(self):
        for message in self.messages:
            message.delete()
        self.redis.delete('conversations:%d' % self.id)
        self.redis.delete('conversations:%d:messages' % self.id)
        self.redis.zrem('operators:%d:conversations' % self.operator.id, self.id)

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
        for m in redis_iter(self.redis, 'conversations:%d:messages' % self.id, ZSET):
            messages[datetime.fromtimestamp(int(m[1]))] = Message(int(m[0]))
        return messages

    def __eq__(self, other):
        return self.id == other.id


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


class Operator:
    def __init__(self, id_, redis_=None):
        self.id = id_
        self.redis = redis_ if redis_ is not None else get_redis_connection()

    def new_conversation(self):
        """ return new Conversation object for operator """
        conversation = Conversation.create(self)
        return conversation

    def regenerate_token(self):
        """ Regenerate operator token """
        self.redis.hset('operators:%d' % self.id, 'token', random_token())

    @property
    def token(self):
        """ return current token """
        return self.redis.hget('operators:%d' % self.id, 'token').decode()

    @property
    def name(self):
        return self.redis.hget('operators:%d' % self.id, 'name').decode()

    @name.setter
    def name(self, name):
        self.redis.hset('operators:%d' % self.id, 'name', name)

    @property
    def conversations(self):
        conversations = OrderedDict()
        for c in redis_iter(self.redis, 'operators:%d:conversations' % self.id, ZSET):
            conversations[datetime.fromtimestamp(int(c[1]))] = Conversation(int(c[0]))
        return conversations

    @classmethod
    def create(cls, name):
        redis_ = get_redis_connection()
        last_id = redis_.get('last_operator_id')
        last_id = int(last_id) if last_id is not None else 0
        redis_.hmset('operators:%d' % last_id, {'name': name,
                                                'token': random_token()})
        redis_.zadd('operators_list', last_id, time.time())
        redis_.incr('last_operator_id')
        return cls(last_id, redis_)

    @classmethod
    def delete(cls, operator):
        redis_ = get_redis_connection()
        for time, conversation in operator.conversations:
            Conversation.delete(conversation)
        redis_.delete('operators:%d' % operator.id)
        redis_.delete('operators:%d:conversations' % operator.id)
        redis_.zrem('operators_list', operator.id)

    @classmethod
    def list(cls):
        redis_ = get_redis_connection()
        operators = OrderedDict()
        for o in redis_iter(redis_, 'operators_list', ZSET):
            operators[datetime.fromtimestamp(int(o[1]))] = cls(int(o[0]))
        return operators


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
