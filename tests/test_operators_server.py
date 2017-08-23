from unittest import TestCase
from telegram_bot_constructor import set_redis_connection, get_redis_connection
from redis import Redis
from telegram_bot_constructor.operators_server import Operator
import uuid

set_redis_connection(Redis(host='127.0.0.1', port=6379, db=9))
redis_ = get_redis_connection()
redis_.flushdb()


class TestOperator(TestCase):
    def setUp(self):
        self.operator = Operator.create(uuid.uuid4().hex)

    def test_creation(self):
        self.assertIsInstance(self.operator, Operator)
        self.assertTrue(self.operator in Operator.list())

    def test_renaming(self):
        self.assertIsInstance(self.operator.name, str)
        self.assertEqual(len(self.operator.name), 32)
        old_name = self.operator.name
        self.operator.name = uuid.uuid4().hex
        self.assertNotEqual(old_name, self.operator.name)
        self.assertIsInstance(self.operator.name, str)
        self.assertEqual(len(self.operator.name), 32)

    def test_token_regeneration(self):
        self.assertIsInstance(self.operator.token, str)
        self.assertEqual(len(self.operator.token), 16)
        old_token = self.operator.token
        self.operator.regenerate_token()
        self.assertNotEqual(old_token, self.operator.token)
        self.assertIsInstance(self.operator.token, str)
        self.assertEqual(len(self.operator.token), 16)

    def test_deletion(self):
        self.operator.delete()
        self.assertFalse(self.operator in Operator.list())
