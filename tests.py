import os
import sys
import threading
import unittest
from unittest.mock import Mock
import logging
import time

from logline import LogLine
from logkeep import LogKeep
from log_consumer import LogConsumer
from top_n_sections import TopNSectionsStatistic
from average_request_size_statistic import AverageRequestSizeStatistic
from monitor import HTTPLogMonitor
from alert import AlertState
from alerter import Alerter

logger = logging.getLogger()
logger.level = logging.DEBUG
stream_handler = logging.StreamHandler(sys.stdout)
logger.addHandler(stream_handler)

def generate_loglines(section: str = '/api', num_lines: int = 5, sleep: int = 0):
        loglines = []
        for _ in range(num_lines):
            line = '\"10.0.0.2\",\"-\",\"apache\",{},\"GET {} HTTP/1.0\",200,1234'.format(round(time.time()), section)
            log_line = LogLine.from_line(line)
            loglines += [log_line]
            if sleep:
                time.sleep(sleep)

        return loglines

class LogLineTest(unittest.TestCase):
    def test_from_line(self):
        line = '\"10.0.0.2\",\"-\",\"apache\",1549573860,\"GET /api/user HTTP/1.0\",200,1234'
        log_line = LogLine.from_line(line)
        self.assertEqual(log_line.bytes, 1234)

    def test_get_section(self):
        log_line = LogLine(request='GET /api/user HTTP/1.0')
        section = log_line.get_section()
        self.assertEqual(section, '/api')

class LogKeepTest(unittest.TestCase):
    def test_get_recent_loglines(self):
        logkeep = LogKeep()
        for _ in range(3):
            logkeep.add_logline(LogLine())
            time.sleep(1)

class LogConsumerTest(unittest.TestCase):
    def test_write_to_logkeep(self):
        test_log = 'consumertest.log'
        with open(test_log, 'w', 1) as log:
            for _ in range(10):
                log.write('\"10.0.0.2\",\"-\",\"apache\",{},\"GET /api/user HTTP/1.0\",200,1234\n'.format(round(time.time())))

        self.logkeep = Mock()
        self.consumer = LogConsumer(test_log, self.logkeep)
        self.consumer.consume_next_lines()
        self.consumer.pygtail = None
        self.logkeep.add_logline.assert_called()

        os.remove(test_log)
        os.remove('{}.offset'.format(test_log))

class TopSectionStatisticTest(unittest.TestCase):
    def test_calculate_statistic(self):
        statistic = TopNSectionsStatistic()
        loglines = []
        loglines += generate_loglines(section='/api', num_lines=2, sleep=1)
        loglines += generate_loglines(section='/report', num_lines=1, sleep=1)

        section_counts = statistic._add_counts_for_new_lines(loglines)
        top_n_sections = statistic.get_top_n_fields(section_counts)
        self.assertEqual(len(top_n_sections), 1)

        section, hits = top_n_sections[0]
        self.assertEqual(section, '/api')
        self.assertEqual(hits, 2)

class AverageRequestSizeStatisticTest(unittest.TestCase):
    def test_calculate_statistic(self):
        statistic = AverageRequestSizeStatistic()
        
        loglines = []
        loglines += generate_loglines(num_lines=2, sleep=1)
        loglines += generate_loglines(num_lines=1, sleep=1)

        avg_request_size = statistic._get_avg_request_size(loglines)
        self.assertEqual(avg_request_size, 1234)

class HTTPLogMonitorTest(unittest.TestCase):
    def test_calculate_stats_get_recent_loglines_from_logkeep(self):
        logkeep = Mock()
        monitor = HTTPLogMonitor(None, logkeep, None, [])

        monitor._calculate_stats()
        logkeep.read_recent_loglines.assert_called_once()

    def test_calculate_stats_calls_traffic_statistic(self):
        statistic = Mock() 
        monitor = HTTPLogMonitor(None, Mock(), None, [statistic])

        monitor._calculate_stats()
        statistic.calculate_statistic.assert_called_once()

class AlerterTest(unittest.TestCase):
    def test_check_if_alert_under_threshold_no_alert(self):
        alerter = Alerter(alert_check_interval=120, high_traffic_threshold=10)
        loglines = generate_loglines(num_lines=100, sleep=0)

        has_alert = alerter.check_if_alert(loglines)
        self.assertFalse(has_alert)
        self.assertIsNone(alerter.last_alert)

    def test_check_if_alert_over_threshold_has_alert(self):
        alerter = Alerter(alert_check_interval=120, high_traffic_threshold=10)

        loglines_at_threshold = alerter.high_traffic_threshold * alerter.alert_check_interval
        loglines = generate_loglines(num_lines=loglines_at_threshold+1, sleep=0)

        has_alert = alerter.check_if_alert(loglines)

        self.assertIsNotNone(alerter.last_alert)
        self.assertEqual(alerter.last_alert.state, AlertState.HIGH_TRAFFIC)

    def test_check_alert_recover_from_high_traffic(self):
        alerter = Alerter(alert_check_interval=120, high_traffic_threshold=10)

        loglines_at_threshold = alerter.high_traffic_threshold * alerter.alert_check_interval
        loglines = generate_loglines(num_lines=loglines_at_threshold+1, sleep=0)

        has_alert = alerter.check_if_alert(loglines)
        self.assertIsNotNone(alerter.last_alert)

        loglines = generate_loglines(num_lines=100, sleep=0)
        has_alert = alerter.check_if_alert(loglines)

        self.assertIsNotNone(alerter.last_alert)
        self.assertEqual(alerter.last_alert.state, AlertState.RECOVERED)

    def test_check_if_alert_no_duplicate_alerts_created(self):
        alerter = Alerter(alert_check_interval=120, high_traffic_threshold=10)

        loglines_at_threshold = alerter.high_traffic_threshold * alerter.alert_check_interval
        loglines = generate_loglines(num_lines=loglines_at_threshold+1, sleep=0)

        # Generate first alert
        has_alert = alerter.check_if_alert(loglines)
        first_alert = alerter.last_alert

        self.assertIsNotNone(alerter.last_alert)
        self.assertEqual(alerter.last_alert.state, AlertState.HIGH_TRAFFIC)

        # Try to generate second alert
        alerter.check_if_alert(loglines)
        self.assertEqual(first_alert.time, alerter.last_alert.time)
