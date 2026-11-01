"""Full mock election night (simulated 6:30 PM-2:00 AM ET) through the real poller and combiner."""
import tempfile, unittest
from live import mock


class TestMockElectionNight(unittest.TestCase):
    def test_all_scenarios(self):
        live, timeline = mock.run(tempfile.mkdtemp())
        failed = [name for name, ok in mock.checks(live, timeline) if not ok]
        self.assertEqual(failed, [])


if __name__ == '__main__':
    unittest.main()
