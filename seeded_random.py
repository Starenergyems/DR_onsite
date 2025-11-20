"""Seeded random number generator utility.

This module exposes a small helper for generating deterministic sequences of
random integers based on a provided seed. It also offers a simple CLI for
printing generated numbers either line-by-line or as JSON.
"""

from __future__ import annotations

import argparse
import json
from random import Random
from typing import Iterable, List


def generate_random_numbers(
    seed: int,
    count: int,
    lower: int = 0,
    upper: int = 100,
) -> List[int]:
    """Generate a deterministic list of pseudo-random integers.

    Args:
        seed: Seed to initialize the RNG.
        count: How many numbers to generate. Must be non-negative.
        lower: Inclusive lower bound of the range.
        upper: Inclusive upper bound of the range.

    Returns:
        A list of integers drawn uniformly from the inclusive range
        ``[lower, upper]``.

    Raises:
        ValueError: If ``count`` is negative or if ``lower`` is greater than
            ``upper``.
    """

    if count < 0:
        raise ValueError("count must be non-negative")
    if lower > upper:
        raise ValueError("lower cannot be greater than upper")

    rng = Random(seed)
    return [rng.randint(lower, upper) for _ in range(count)]


def _format_numbers(numbers: Iterable[int], as_json: bool) -> str:
    if as_json:
        return json.dumps({"numbers": list(numbers)})
    return "\n".join(str(n) for n in numbers)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True, help="Seed for the RNG")
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="How many numbers to generate (default: 10)",
    )
    parser.add_argument(
        "--lower",
        type=int,
        default=0,
        help="Inclusive lower bound of the generated numbers (default: 0)",
    )
    parser.add_argument(
        "--upper",
        type=int,
        default=100,
        help="Inclusive upper bound of the generated numbers (default: 100)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output the generated numbers as a JSON object",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    numbers = generate_random_numbers(args.seed, args.count, args.lower, args.upper)
    print(_format_numbers(numbers, args.json))


if __name__ == "__main__":
    main()
