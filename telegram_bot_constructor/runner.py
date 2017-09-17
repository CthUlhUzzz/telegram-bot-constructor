from . import get_redis_connection
from . import constructor
from .operators_server import Operator
from .operators_server import OperatorsDispatcher
from .helpers import StoredObject
from telegram import Bot
from telegram_bot_vm.state import BotState
from telegram_bot_vm.bot import Bot
from datetime import date
import time

running_bots = {}


class BotTemplateNotSelected(Exception):
    pass


class BotRunnerContext(StoredObject, BotState):
    MNEMONIC = 'bot_context'

    def init(self, name):
        self.bot = None
        self.name = name
        self.redis.rpush('bot_contexts_list', self.id)

    def clean_up(self):
        for operator in self.operators:
            operator.delete()
        self.redis.delete('bot_contexts:%d:name' % self.id)
        self.redis.delete('bot_contexts:%d:bot_template' % self.id)
        self.redis.delete('bot_contexts:%d:token' % self.id)
        self.redis.delete('bot_contexts:%d:operators' % self.id)
        self.redis.delete('bot_contexts:%d:visits' % self.id)
        self.redis.delete('bot_contexts:%d:chats' % self.id)
        self.redis.lrem('bot_contexts_list', self.id)

    @property
    def running(self):
        return self.bot is not None

    @property
    def bot(self):
        if self.id in running_bots:
            return running_bots[self.id]

    @bot.setter
    def bot(self, bot):
        if bot is None:
            if self.id in running_bots:
                del running_bots[self.id]
        else:
            running_bots[self.id] = bot

    @property
    def name(self):
        n = self.redis.get('bot_contexts:%d:name' % self.id)
        if n is not None:
            return n.decode()

    @name.setter
    def name(self, name):
        self.redis.set('bot_contexts:%d:name' % self.id, name)

    @property
    def token(self):
        t = self.redis.get('bot_contexts:%d:token' % self.id)
        if t is not None:
            return t.decode()

    @token.setter
    def token(self, token):
        Bot._validate_token(token)
        self.redis.set('bot_contexts:%d:token' % self.id, token)

    @property
    def bot_template(self):
        bot_template_id = self.redis.get('bot_contexts:%d:bot_template' % self.id)
        if bot_template_id is not None:
            return constructor.BotTemplate(int(bot_template_id))

    @bot_template.setter
    def bot_template(self, bot_template):
        if bot_template is None:
            self.redis.delete('bot_contexts:%d:bot_template' % self.id)
        else:
            self.redis.set('bot_contexts:%d:bot_template' % self.id, bot_template.id)

    def add_operator(self, operator):
        if operator not in self.operators:
            self.redis.rpush('bot_contexts:%d:operators' % self.id, operator.id)
        else:
            raise OperatorAlreadyAdded

    def delete_operator(self, operator):
        self.redis.lrem('bot_contexts:%d:operators' % self.id, operator.id)

    @property
    def operators(self):
        operators = self.redis.lrange('bot_contexts:%d:operators' % self.id, 0, -1)
        return tuple(Operator(int(o)) for o in operators)

    @classmethod
    def list(cls):
        redis_ = get_redis_connection()
        bot_contexts = redis_.lrange('bot_contexts_list', 0, -1)
        return tuple(cls(int(c)) for c in bot_contexts)

    def get_visits_per_day(self, date_):
        visits = self.redis.hget('bot_contexts:%d:visits', date_.isoformat())
        return 0 if visits is None else int(visits)

    def run(self):
        if not self.running:
            if self.bot_template is not None:
                actions = self.bot_template.compile()
                self.bot = Bot(actions, self,
                               additioanal_properties={'operators_dispatcher': OperatorsDispatcher(self.operators),
                                                       'bot_context_id': self.id})
                self.bot.run(self.token)
            else:
                raise BotTemplateNotSelected

    def stop(self):
        if self.running:
            self.bot.stop()
            self.bot = None

    def add_chat(self, chat):
        self.redis.rpush('bot_contexts:%d:chats' % self.id, chat)

    @property
    def chats(self):
        chats = self.redis.lrange('bot_contexts:%d:chats' % self.id, 0, -1)
        return tuple(int(c) for c in chats)

    def mail_all(self, message):
        """ Send message to all chats """
        if self.running:
            self.bot.mail_all(message)

    def increment_visits(self):
        self.redis.hincrby('bot_contexts:%d:visits' % self.id,
                           date.fromtimestamp(time.time()).isoformat(), 1)


class OperatorAlreadyAdded(Exception):
    pass


def is_operator_locked(operator):
    for context in BotRunnerContext.list():
        for oper in context.operators:
            if oper == operator:
                return True
    return False


def is_bot_template_locked(bot_template):
    for context in BotRunnerContext.list():
        if context.bot_template == bot_template:
            return True
    return False
