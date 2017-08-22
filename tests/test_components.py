from unittest import TestCase

from redis import Redis

from telegram_bot_constructor import set_redis_connection, get_redis_connection
from telegram_bot_constructor.constructor import COMPONENTS_LIST, \
    add_component, delete_component, get_component

set_redis_connection(Redis(host='127.0.0.1', port=6379, db=9))
get_redis_connection().flushdb()


class TestComponents(TestCase):
    def test_functions(self):
        for type_ in COMPONENTS_LIST:
            component = add_component(type_)
            self.assertIsInstance(component, type_)
            new_component = get_component(component.id)
            self.assertIsInstance(new_component, type_)
            self.assertEqual(component, new_component)
            delete_component(component)
            component = get_component(component.id)
            self.assertIsNone(component)
