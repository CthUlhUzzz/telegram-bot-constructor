from unittest import TestCase

from redis import Redis

from telegram_bot_constructor import set_redis_connection, get_redis_connection
from telegram_bot_constructor.constructor import SendMessage
from telegram_bot_constructor.constructor import Screen, add_screen, delete_screen, get_screen

set_redis_connection(Redis(host='127.0.0.1', port=6379, db=9))
get_redis_connection().flushdb()


class TestComponents(TestCase):
    def test_functions(self):
        screen = add_screen()
        self.assertIsInstance(screen, Screen)
        new_screen = get_screen(screen.id)
        self.assertIsInstance(new_screen, Screen)
        self.assertEqual(screen, new_screen)
        delete_screen(screen)
        screen = get_screen(screen.id)
        self.assertIsNone(screen)

    def test_components(self):
        screen = add_screen()
        self.assertIsInstance(screen.components, list)
        self.assertEqual(len(screen.components), 0)
        screen.add_component(SendMessage)
        self.assertIsInstance(screen.components, list)
        self.assertEqual(len(screen.components), 1)
        self.assertIsInstance(screen.components[0], SendMessage)
        screen.delete_component(screen.components[0])
        self.assertIsInstance(screen.components, list)
        self.assertEqual(len(screen.components), 0)
