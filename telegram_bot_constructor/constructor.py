from .helpers import StoredObject, get_redis_connection
from telegram_bot_vm.actions import *
from .operators_server import OperatorDialogAction


class BaseComponent(StoredObject):
    MNEMONIC = 'component'

    @property
    def type(self):
        return self.redis.get('components:%d:type' % self.id).decode()

    @type.setter
    def type(self, type_):
        self.redis.set('components:%d:type' % self.id, type_)

    def init(self, *args, **kwargs):
        self.type = type(self).__name__

    def clean_up(self):
        self.redis.delete('components:%d:type' % self.id)


class SendMessage(BaseComponent):
    """ Send message to client """

    def init(self, text):
        super().init()
        self.text = text

    @property
    def text(self):
        return self.redis.get('components:%d:text' % self.id, ).decode()

    @text.setter
    def text(self, text):
        self.redis.set('components:%d:text' % self.id, text)

    def clean_up(self):
        super().clean_up()
        self.redis.delete('components:%d:text' % self.id)


class GetInput(BaseComponent):
    """ Wait input from user and store it into variable """

    def init(self, variable_name):
        super().init()
        self.variable_name = variable_name

    @property
    def variable_name(self):
        return self.redis.get('components:%d:variable_name' % self.id).decode()

    @variable_name.setter
    def variable_name(self, variable_name):
        self.redis.set('components:%d:variable_name' % self.id, variable_name)

    def clean_up(self):
        super().clean_up()
        self.redis.delete('components:%d:variable_name' % self.id)


class ForwardToScreen(BaseComponent):
    """ Conditional and unconditional forward to other screen
    If no condition_regex - unconditional forward
    else if variable match condition_regex - conditional forward
    else - ignore """

    def init(self, variable_name, target_screen, condition_regex):
        super().init()
        self.variable_name = variable_name
        self.target_screen = target_screen
        self.condition_regex = condition_regex

    @property
    def variable_name(self):
        return self.redis.get('components:%d:variable_name' % self.id).decode()

    @variable_name.setter
    def variable_name(self, variable_name):
        self.redis.set('components:%d:variable_name' % self.id, variable_name)

    @property
    def target_screen(self):
        return int(self.redis.get('components:%d:target_screen' % self.id))

    @target_screen.setter
    def target_screen(self, screen):
        self.redis.set('components:%d:target_screen' % self.id, screen.id)

    @property
    def condition_regex(self):
        return self.redis.get('components:%d:condition' % self.id).decode()

    @condition_regex.setter
    def condition_regex(self, condition):
        self.redis.set('components:%d:condition' % self.id, condition)

    def clean_up(self):
        super().clean_up()
        self.redis.delete('components:%d:variable_name' % self.id)
        self.redis.delete('components:%d:target_screen' % self.id)
        self.redis.delete('components:%d:condition' % self.id)


class OperatorDialog(BaseComponent):
    """ Connect free operator to dialog with user """

    def init(self, start_message, stop_message, fail_message):
        super().init()
        self.start_message = start_message
        self.stop_message = stop_message
        self.fail_message = fail_message

    @property
    def start_message(self):
        return self.redis.get('components:%d:start_message' % self.id).decode()

    @start_message.setter
    def start_message(self, start_message):
        self.redis.set('components:%d:start_message' % self.id, start_message)

    @property
    def stop_message(self):
        return self.redis.get('components:%d:stop_message' % self.id).decode()

    @stop_message.setter
    def stop_message(self, stop_message):
        self.redis.set('components:%d:stop_message' % self.id, stop_message)

    @property
    def fail_message(self):
        return self.redis.get('components:%d:fail_message' % self.id).decode()

    @fail_message.setter
    def fail_message(self, fail_message):
        self.redis.set('components:%d:fail_message' % self.id, fail_message)

    def clean_up(self):
        super().clean_up()
        self.redis.delete('components:%d:start_message' % self.id)
        self.redis.delete('components:%d:stop_message' % self.id)
        self.redis.delete('components:%d:fail_message' % self.id)


_COMPONENTS_TYPES_MAP = {'SendMessage': SendMessage,
                         'GetInput': GetInput,
                         'ForwardToScreen': ForwardToScreen,
                         'OperatorDialog': OperatorDialog}


def get_component_by_id(id_):
    redis_ = get_redis_connection()
    type_ = redis_.get('components:%d:type' % id_).decode()
    return _COMPONENTS_TYPES_MAP[type_](id_)


class Screen(StoredObject):
    MNEMONIC = 'screen'

    def init(self, name):
        self.name = name

    @property
    def name(self):
        return self.redis.get('screens:%d:name' % self.id).decode()

    @name.setter
    def name(self, name):
        self.redis.set('screens:%d:name' % self.id, name)

    def clean_up(self):
        for component in self.components:
            component.delete()
        self.redis.delete('screens:%d:name' % self.id)
        self.redis.delete('screens:%d:components' % self.id)

    def add_component(self, component):
        """ Add component to screen """
        components_count = int(self.redis.zcard('screens:%d:components' % self.id))
        self.redis.zadd('screens:%d:components' % self.id, component.id, components_count)

    @property
    def components(self):
        """ Return components """
        result = []
        components = self.redis.zrange('screens:%d:components' % self.id, 0, -1)
        for c in components:
            result.append(get_component_by_id(int(c)))
        return tuple(result)

    def change_component_position(self, component, target_index):
        """ change index for component in screen """
        component_index = self.redis.zrank('screens:%d:components' % self.id, component.id)
        components_count = self.redis.zcard('screens:%d:components' % self.id)
        assert 0 <= target_index < components_count
        if component_index is not None:
            if component_index < target_index:
                center_components = self.redis.zrange('screens:%d:components' % self.id,
                                                      component_index + 1, target_index)
                for c in center_components:
                    self.redis.zincrby('screens:%d:components' % self.id, int(c), -1)
                self.redis.zincrby('screens:%d:components' % self.id, component.id, target_index - component_index)
            elif component_index > target_index:
                center_components = self.redis.zrange('screens:%d:components' % self.id,
                                                      target_index, component_index - 1)
                for c in center_components:
                    self.redis.zincrby('screens:%d:components' % self.id, int(c), +1)
                self.redis.zincrby('screens:%d:components' % self.id, component.id, target_index - component_index)

    def delete_component(self, component):
        """ Delete component from screen """
        component_index = self.redis.zrank('screens:%d:components' % self.id, component.id)
        if component_index is not None:
            self.redis.zrem('screens:%d:components' % self.id, component.id)
            tail_components = self.redis.zrange('screens:%d:components' % self.id, component_index, -1)
            for c in tail_components:
                self.redis.zincrby('screens:%d:components' % self.id, int(c), -1)
            component.delete()


class BotTemplate(StoredObject):
    MNEMONIC = 'bot_template'

    @property
    def start_screen(self):
        return self.screens[0]

    def delete_screen(self, screen):
        """ Delete screen from bot template """
        self.redis.lrem('bot_templates:%d:screens' % self.id, screen.id)
        screen.delete()

    def add_screen(self, screen):
        """ Add new screen to bot template """
        self.redis.rpush('bot_templates:%d:screens' % self.id, screen.id)

    @property
    def screens(self):
        """ return screens iterator """
        screens = self.redis.lrange('bot_templates:%d:screens' % self.id, 0, -1)
        return tuple(Screen(int(screen)) for screen in screens)

    def compile(self):
        """ return actions for execution in Virtual Machine """

        def calculate_forward_position(screens, screen=None):
            position = 0
            if screen is not None:
                screen_index = screens.index(screen)
                screens = self.screens[:screen_index]
            for s in screens:
                position += len(s.components) + 1
            return position

        actions = []
        screens = self.screens
        for screen in screens:
            for action in screen.components:
                if isinstance(action, SendMessage):
                    actions.append(SendMessageAction(action.text))
                elif isinstance(action, GetInput):
                    actions.append(GetInputAction(action.variable_name))
                elif isinstance(action, ForwardToScreen):
                    actions.append(ForwardToPositionAction(calculate_forward_position(screens, screen),
                                                           action.variable_name,
                                                           action.condition_regex))
                elif isinstance(action, OperatorDialog):
                    actions.append(OperatorDialogAction(action.start_message,
                                                        action.stop_message,
                                                        action.fail_message))
            actions.append(ForwardToPositionAction(calculate_forward_position(screens)))
        return actions

    def init(self, name):
        """ add bot template to db and return """
        self.name = name
        self.redis.rpush('bot_templates_list', self.id)
        self.add_screen(Screen.create('Start screen'))

    def clean_up(self):
        for screen in self.screens:
            screen.delete()
        self.redis.lrem('bot_templates_list', self.id)
        self.redis.delete('bot_templates:%d:screens' % self.id)
        self.redis.delete('bot_templates:%d:name' % self.id)

    @property
    def name(self):
        return self.redis.get('bot_templates:%d:name' % self.id).decode()

    @name.setter
    def name(self, name):
        self.redis.set('bot_templates:%d:name' % self.id, name)

    @classmethod
    def list(cls):
        redis_ = get_redis_connection()
        bot_templates_list = redis_.lrange('bot_templates_list', 0, -1)
        return tuple(cls(int(t)) for t in bot_templates_list)
