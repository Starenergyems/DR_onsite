import unittest

from seeded_random import generate_random_numbers


class GenerateRandomNumbersTests(unittest.TestCase):
    def test_reproducible_output(self):
        first = generate_random_numbers(seed=42, count=5, lower=1, upper=6)
        second = generate_random_numbers(seed=42, count=5, lower=1, upper=6)
        self.assertEqual(first, second)

    def test_within_bounds(self):
        numbers = generate_random_numbers(seed=7, count=50, lower=-5, upper=5)
        self.assertTrue(all(-5 <= n <= 5 for n in numbers))

    def test_negative_count_raises(self):
        with self.assertRaises(ValueError):
            generate_random_numbers(seed=1, count=-1)

    def test_lower_greater_than_upper_raises(self):
        with self.assertRaises(ValueError):
            generate_random_numbers(seed=1, count=1, lower=10, upper=5)


if __name__ == "__main__":
    unittest.main()
