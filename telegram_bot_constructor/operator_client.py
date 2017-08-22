import json

from . import get_redis_connection
from .helpers import random_token
from .operators_server import ConversationStopped, OPERATOR_ACCESS_DENIED, \
    OPERATOR_ALREADY_CONNECTED, OPERATOR_STATUSES


class NotAuthenticated(Exception):
    pass


class AccessDenied(Exception):
    pass


class AlreadyConnected(Exception):
    pass


def authentication_check(func):
    def wrapped(self, *args, **kwargs):
        if self.authentication not in OPERATOR_STATUSES:
            raise NotAuthenticated
        elif self.authentication == OPERATOR_ALREADY_CONNECTED:
            raise AlreadyConnected
        elif self.authentication == OPERATOR_ACCESS_DENIED:
            raise AccessDenied
        else:
            return func(self, *args, **kwargs)

    return wrapped


def conversation_check(func):
    def wrapped(self, *args, **kwargs):
        if self.conversation_started:
            return func(self, *args, **kwargs)
        else:
            raise ConversationStopped

    return wrapped


class OperatorInterface:
    def __init__(self, operator_token, redis_=None):
        self.redis = redis_ if redis_ is not None else get_redis_connection()
        self.operator_token = operator_token
        self.conversation_started = False
        self.incoming_messages = []
        self.authentication = None

    @authentication_check
    @conversation_check
    def receive_messages(self):
        """ Return incoming messages from user """
        messages = self.incoming_messages
        self.incoming_messages = []
        return messages

    @authentication_check
    @conversation_check
    def send_message(self, text):
        """ Send message to user """
        self.redis.publish('message_to_user', json.dumps((self.operator_token, text)))

    @authentication_check
    @conversation_check
    def stop_conversation(self):
        """ Stop conversation if started """
        self.redis.publish('conversation_stopped_by_operator', json.dumps(self.operator_token))
        self.conversation_started = False

    def __eq__(self, other):
        return id(self) == id(other)


class OperatorInterfaceDispatcher:
    def __init__(self):
        self.redis = get_redis_connection()
        self.pubsub = self.redis.pubsub(ignore_subscribe_messages=True)
        self.interfaces = {}  # Operator token to conversation map
        self.authentications = {}
        self.pubsub.subscribe('authentication_result', 'conversation_started',
                              'message_to_operator', 'conversation_stopped_by_user')

    def get_interface(self, operator_token):
        """ Get interface for given operator """
        if operator_token not in self.interfaces:
            auth_token = random_token()
            self.redis.publish('authentication', json.dumps((operator_token, auth_token)))
            interface = OperatorInterface(operator_token)
            self.authentications[auth_token] = interface
            self.interfaces[operator_token] = interface
            return interface

    def release_interface(self, interface):
        """ Release interface to pool """
        self.redis.publish('disconnected', json.dumps(interface.operator_token))
        del self.interfaces[interface.operator_token]

    def update(self):
        """ Update interfaces state """
        for _ in range(25):
            message = self.pubsub.get_message()
            if message is not None:
                if message['type'] == 'message':
                    channel = message['channel'].decode()
                    message = json.loads(message['data'].decode())
                    # Get authentication result
                    if channel == 'authentication_result':
                        token, result = message
                        if token in self.authentications:
                            if result in OPERATOR_STATUSES:
                                self.authentications[token].authentication = result
                                del self.authentications[token]
                    # Conversation started by user
                    elif channel == 'conversation_started':
                        # for interface in self.interfaces:
                        if message in self.interfaces:
                            self.interfaces[message].conversation_started = True
                    # Conversation stopped by user
                    elif channel == 'conversation_stopped_by_user':
                        if message in self.interfaces:
                            self.interfaces[message].conversation_started = False
                    # Get message from user
                    elif channel == 'message_to_operator':
                        operator_token, text = message
                        if operator_token in self.interfaces:
                            self.interfaces[operator_token].incoming_messages.append(text)
