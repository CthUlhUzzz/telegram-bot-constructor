from telegram_bot_constructor import get_redis_connection
from telegram_bot_constructor.helpers import redis_iter, ZSET


class BaseComponent:
    def __init__(self, id_, redis_=None):
        self.id = id_
        self.redis = redis_ if redis_ is not None else get_redis_connection()
        assert self.type == type(self).__name__

    def __eq__(self, other):
        return self.id == other.id

    @property
    def type(self):
        return self.redis.hget('components:%d' % self.id, 'type').decode()

    @classmethod
    def create(cls):
        """ add component to db and return """
        redis_ = get_redis_connection()
        last_id = redis_.get('last_message_id')
        last_id = int(last_id) if last_id is not None else 0
        redis_.hset('components:%d' % last_id, 'type', cls.__name__)
        redis_.incr('last_component_id')
        return cls(last_id)

    def delete(self):
        self.redis.delete('components:%d' % self.id)


class SendMessage(BaseComponent):
    """ Send message to client """

    @property
    def text(self):
        return self.redis.hget('components:%d' % self.id, 'text').decode()

    @text.setter
    def text(self, text):
        self.redis.hset('components:%d' % self.id, 'text', text)


class GetInput(BaseComponent):
    """ Wait input from user and store it into variable """

    @property
    def variable_name(self):
        return self.redis.hget('components:%d' % self.id, 'variable_name').decode()

    @variable_name.setter
    def variable_name(self, variable_name):
        self.redis.hset('components:%d' % self.id, 'variable_name', variable_name)


class ForwardToScreen(BaseComponent):
    """ Conditional and unconditional forward to other screen
    If no condition_regex - unconditional forward
    else if variable match condition_regex - conditional forward
    else - ignore """

    @property
    def variable_name(self):
        return self.redis.hget('components:%d' % self.id, 'variable_name').decode()

    @variable_name.setter
    def variable_name(self, variable_name):
        self.redis.hset('components:%d' % self.id, 'variable_name', variable_name)

    @property
    def target_screen(self):
        return int(self.redis.hget('components:%d' % self.id, 'target_screen'))

    @target_screen.setter
    def target_screen(self, screen):
        self.redis.hset('components:%d' % self.id, 'target_screen', screen.id)

    @property
    def condition_regex(self):
        return self.redis.hget('components:%d' % self.id, 'condition').decode()

    @condition_regex.setter
    def condition_regex(self, condition):
        self.redis.hset('components:%d' % self.id, 'condition', condition)


class OperatorDialog(BaseComponent):
    """ Connect free operator to dialog with user """


_COMPONENTS_TYPES_MAP = {'SendMessage': SendMessage,
                         'GetInput': GetInput,
                         'ForwardToScreen': ForwardToScreen,
                         'OperatorDialog': OperatorDialog}


class Screen:
    def __init__(self, id_, redis_=None):
        self.id = id_
        self.redis = redis_ if redis_ is not None else get_redis_connection()

    @classmethod
    def create(cls, name):
        redis_ = get_redis_connection()
        last_id = redis_.get('last_screen_id')
        last_id = int(last_id) if last_id is not None else 0
        redis_.hset('screens:%d' % last_id, 'name', name)
        redis_.incr('last_screen_id')
        return cls(last_id, redis_)

    def delete(self):
        for component in self.components:
            component.delete()
        self.redis.delete('screens:%d:components' % self.id)
        self.redis.delete('screens:%d' % self.id)

    def add_component(self, component):
        """ Add component to screen """
        components_count = int(self.redis.zcard('screens:%d:components' % self.id))
        self.redis.zadd('screens:%d:components' % self.id, component.id, components_count)

    @property
    def components(self):
        """ Return components """
        result = []
        for index, component in redis_iter(self.redis, 'screens:%d:components' % self.id, ZSET):
            type_ = self.redis.hget('components:%d' % int(component), 'type').decode()
            result.append(_COMPONENTS_TYPES_MAP[type_](int(component)))
        return result

    def change_position(self, component, target_index):
        """ change index for component in screen """
        component_index = self.redis.zrank('screens:%d:components' % self.id, component.id)
        components_count = self.redis.zcard('screens:%d:components' % self.id)
        assert component_index != target_index
        assert 0 >= target_index < components_count
        if component.index is not None:
            if component_index < target_index:
                center_components = self.redis.zrange('screens:%d:components' % self.id,
                                                      int(component_index) + 1, target_index)
                for c in center_components:
                    self.redis.zincrby('screens:%d:components' % self.id, int(c), -1)
                self.redis.zincrby('screens:%d:components' % self.id, component.id, + (target_index - component_index))
            elif component_index > target_index:
                center_components = self.redis.zrange('screens:%d:components' % self.id,
                                                      int(component_index) - 1, target_index)
                for c in center_components:
                    self.redis.zincrby('screens:%d:components' % self.id, int(c), +1)
                self.redis.zincrby('screens:%d:components' % self.id, component.id, - (component_index - target_index))

    def delete_component(self, component):
        """ Delete component from screen """
        component_index = self.redis.zrank('screens:%d:components' % self.id, component.id)
        if component.index is not None:
            tail_components = self.redis.zrange('screens:%d:components' % self.id, int(component_index), -1)
            for c in tail_components:
                self.redis.zincrby('screens:%d:components' % self.id, int(c), -1)

        BaseComponent.delete(component.id)

    def __eq__(self, other):
        return self.id == other.id


class BotTemplate:
    def __init__(self, id_, redis_=None):
        self.redis = redis_ if redis_ is not None else get_redis_connection()
        self.id = id_

    def delete_screen(self, screen):
        """ Delete screen from bot template """
        if self.start_screen is not None and screen == self.start_screen:
            self.start_screen = None
        self.redis.srem('bot_templates:%d:screens' % self.id, screen.id)
        screen.delete()

    def add_screen(self, name):
        """ Add new screen to bot template """
        screen = Screen.create(name)
        self.redis.sadd('bot_templates:%d:screens' % self.id, screen.id, screen.id)
        return screen

    @property
    def start_screen(self):
        """ return start screen if set, else None """
        screen_id = self.redis.hget('bot_templates:%d' % self.id, 'start_screen')
        return Screen(screen_id)

    @start_screen.setter
    def start_screen(self, screen):
        """ set start screen """
        if screen in self.screens:
            self.redis.hset('bot_templates:%d' % self.id, 'start_screen', screen.id)
        elif screen is None:
            self.redis.hset('bot_templates:%d' % self.id, 'start_screen', '')

    def __eq__(self, other):
        return self.id == other.id

    @property
    def screens(self):
        """ return screens iterator """
        screens = self.redis.srange('bot_templates:%d:screens', 0, -1)
        return screens

    def compile(self):
        """ return actions for execution in Virtual Machine """

    @classmethod
    def create(cls, name):
        """ add bot template to db and return """
        redis_ = get_redis_connection()
        last_id = redis_.get('last_bot_template_id')
        last_id = int(last_id) if last_id is not None else 0
        redis_.sadd('bot_templates_available', last_id)
        redis_.hset('bot_templates:%d' % last_id, 'name', name)
        redis_.incr('last_bot_template_id')
        return cls(last_id, redis_)

    def delete(self):
        # redis_connection = get_redis_connection()
        for screen in self.screens:
            screen.delete()
        self.redis.delete('bot_templates:%d:screens' % self.id)
        self.redis.delete('bot_templates:%d' % self.id)
        self.redis.srem('bot_templates_available', self.id)
