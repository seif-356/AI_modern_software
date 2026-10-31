from is_prime import is_prime


def test_seven_is_prime():
    assert is_prime(7) == True


def test_ten_is_not_prime():
    assert is_prime(10) == False


def test_two_is_prime():
    assert is_prime(2) == True
