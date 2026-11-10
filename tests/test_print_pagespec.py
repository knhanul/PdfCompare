import unittest

from app.print_engine.pagespec import PageSpecError, parse, parse_multi


class PageSpecTest(unittest.TestCase):
    def test_mixed(self):
        self.assertEqual(parse('1,3,5-8,12', 12), [0, 2, 4, 5, 6, 7, 11])

    def test_open_ranges(self):
        self.assertEqual(parse('-2', 5), [0, 1])
        self.assertEqual(parse('4-', 5), [3, 4])

    def test_odd_even_all(self):
        self.assertEqual(parse('odd', 5), [0, 2, 4])
        self.assertEqual(parse('even', 5), [1, 3])
        self.assertEqual(parse('all', 3), [0, 1, 2])

    def test_errors(self):
        for bad in ('', ' ', '0', '6', '3-2', '1,,2', 'a', '2-9', '1-'  if False else '--'):
            with self.assertRaises(PageSpecError, msg=bad):
                parse(bad, 5)

    def test_multi(self):
        self.assertEqual(parse_multi('L1-2,R3', {'L': 4, 'R': 4}), [('L', 0), ('L', 1), ('R', 2)])
        self.assertEqual(parse_multi('2', {'L': 4, 'R': 4}), [('L', 1)])
        with self.assertRaises(PageSpecError):
            parse_multi('R9', {'L': 4, 'R': 4})


if __name__ == '__main__':
    unittest.main()
