from unittest import TestCase

from redis import Redis

from telegram_bot_constructor import set_redis_connection, get_redis_connection
from telegram_bot_constructor.constructor import Screen
from telegram_bot_constructor.constructor import add_bot_template, delete_bot_template, get_bot_template, BotTemplate

set_redis_connection(Redis(host='127.0.0.1', port=6379, db=9))
get_redis_connection().flushdb()


class TestBotTemplate(TestCase):
    def test_functions(self):
        template = add_bot_template()
        self.assertIsInstance(template, BotTemplate)
        new_template = get_bot_template(template.id)
        self.assertIsInstance(new_template, BotTemplate)
        self.assertEqual(template, new_template)
        delete_bot_template(template)
        template = get_bot_template(template.id)
        self.assertIsNone(template)

    def test_screens(self):
        template = add_bot_template()
        self.assertIsInstance(template.screens, list)
        self.assertEqual(len(template.screens), 0)
        template.add_screen()
        self.assertIsInstance(template.screens, list)
        self.assertEqual(len(template.screens), 1)
        self.assertIsInstance(template.screens[0], Screen)
        template.delete_screen(template.screens[0])
        self.assertIsInstance(template.screens, list)
        self.assertEqual(len(template.screens), 0)

    def test_start_screen(self):
        template = add_bot_template()
        self.assertIsNone(template.start_screen)
        template.add_screen()
        template.start_screen = template.screens[0]
        self.assertIsInstance(template.start_screen, Screen)
