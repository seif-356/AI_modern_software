# AI-generated tests (Claude)
import pytest
from is_prime import is_prime


@pytest.mark.parametrize("n", [2, 3, 5, 13, 97, 7919])
def test_primes_return_true(n):
    assert is_prime(n) is True


@pytest.mark.parametrize("n", [4, 9, 15, 25, 49, 7917])
def test_composites_return_false(n):
    assert is_prime(n) is False


@pytest.mark.parametrize("n", [-7, -1, 0, 1])
def test_numbers_below_two_are_not_prime(n):
    assert is_prime(n) is False
