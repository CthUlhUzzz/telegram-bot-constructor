import time
from collections import OrderedDict
from datetime import date, datetime

from telegram_bot_vm.actions import BaseAction
from telegram_bot_vm.machine import BotVM

from . import get_redis_connection
from .constructor import BotTemplate
from .helpers import redis_iter, SET, ZSET
from .operators_server import Operator
from .operators_server import OperatorsDispatcher

running_bots = {}


class BotRunnerContext:
    def __init__(self, id_, redis_=None):
        self.id = id_
        self.redis = redis_ if redis_ is not None else get_redis_connection()

    @classmethod
    def create(cls, name, bot_template, token):
        redis_ = get_redis_connection()
        last_id = redis_.get('last_bot_context_id')
        last_id = int(last_id) if last_id is not None else 0
        redis_.hmset('bot_contexts:%d' % last_id, {'name': name,
                                                   'bot_template': bot_template.id,
                                                   'token': token})
        redis_.zadd('bot_contexts_list', last_id, time.time())
        redis_.incr('last_bot_context_id')
        return cls(last_id, redis_)

    def delete(self):
        for operator in self.operators:
            operator.delete()
        self.redis.delete('bot_contexts:%d' % self.id)
        self.redis.delete('bot_contexts:%d:operators' % self.id)
        self.redis.zrem('bot_contexts_list', self.id)

    @property
    def running(self):
        return True if self.id in running_bots else False

    @property
    def name(self):
        return self.redis.hget('bot_contexts:%d' % self.id, 'name').decode()

    @name.setter
    def name(self, name):
        self.redis.hset('bot_contexts:%d' % self.id, 'name', name)

    @property
    def token(self):
        return self.redis.hget('bot_contexts:%d' % self.id, 'token').decode()

    @token.setter
    def token(self, token):
        self.redis.hset('bot_contexts:%d' % self.id, 'token', token)

    @property
    def bot_template(self):
        bot_template_id = self.redis.hget('bot_contexts:%d' % self.id, 'bot_template')
        if bot_template_id is not None:
            return BotTemplate(int(bot_template_id))

    @bot_template.setter
    def bot_template(self, bot_template):
        self.redis.hset('bot_contexts:%d' % self.id, 'bot_template', bot_template)

    def add_operator(self, operator):
        self.redis.sadd('bot_contexts:%d:operators' % self.id, operator.id)

    def delete_operator(self, operator):
        self.redis.srem('bot_contexts:%d:operators' % self.id, operator.id)

    @property
    def operators(self):
        operators = []
        for o in redis_iter(self.redis, 'bot_contexts:%d:operators' % self.id, SET):
            operators.append(Operator(int(o[0])))
        return operators

    @classmethod
    def list(cls):
        redis_ = get_redis_connection()
        bot_contexts = OrderedDict()
        for c in redis_iter(redis_, 'bot_contexts_list', ZSET):
            bot_contexts[datetime.fromtimestamp(int(c[1]))] = cls(int(c[0]))
        return bot_contexts

    def get_visits_per_day(self, date_):
        visits = self.redis.hget('bot_contexts:%d:visits', date_.isoformat())
        return 0 if visits is None else int(visits)

    def run(self):
        actions = self.bot_template.compile()
        process = BotVM.run(actions, self.token,
                            add_properties={'operators_dispatcher': OperatorsDispatcher(self.operators),
                                            'bot_context_id': self.id})
        running_bots[self.id] = process

    def stop(self):
        process = running_bots.get(self.id)
        if process is not None:
            process.terminate()
            del running_bots[self.id]


class BotStatisticsAction(BaseAction):
    def exec(self, vm_context):
        redis = get_redis_connection()
        redis.hincr('bot_contexts:%d:visits' % vm_context.bot_context_id, date.fromtimestamp(time.time()).isoformat())
        vm_context += 1
