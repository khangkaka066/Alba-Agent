import unittest

from table import write_table


class TableTests(unittest.TestCase):
    def test_plain_table(self):
        text = write_table(["id", "name"], [[1, "ann"], [2, "bob"]])
        self.assertEqual(text, "id,name\r\n1,ann\r\n2,bob\r\n")

    def test_comma_in_comma_table_is_quoted(self):
        text = write_table(["k", "v"], [["a", "x,y"]])
        self.assertEqual(text, 'k,v\r\na,"x,y"\r\n')

    def test_semicolon_in_semicolon_table_is_quoted(self):
        text = write_table(["k", "v"], [["a", "x;y"]], delimiter=";")
        self.assertEqual(text, 'k;v\r\na;"x;y"\r\n')


if __name__ == "__main__":
    unittest.main()
