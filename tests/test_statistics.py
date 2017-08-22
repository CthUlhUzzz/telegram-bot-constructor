import random
from datetime import date
from unittest import TestCase

from redis import Redis
from telegram_bot_constructor.constructor import add_bot_template

from _old.statistics import BotStatistics
from telegram_bot_constructor import set_redis_connection, get_redis_connection

set_redis_connection(Redis(host='127.0.0.1', port=6379, db=9))
get_redis_connection().flushdb()


class TestStatistics(TestCase):
    def test_statistics(self):
        bot_template = add_bot_template()
        statistics = BotStatistics(bot_template.id)
        incr_count = random.randint(10, 100)
        for _ in range(incr_count):
            statistics.increment_visits()
        self.assertEqual(statistics.get_visits(date.today()), incr_count)
        dates = statistics.get_dates(10)
        self.assertIsInstance(dates, list)
        self.assertEqual(len(dates), 1)
        self.assertIsInstance(dates[0], date)
