from src.services.pool_limits import min_pool_for_division


def test_womens_flyweight_lower_minimum() -> None:
    assert min_pool_for_division("Women's Flyweight") == 8
    assert min_pool_for_division("Welterweight") == 20


def test_nine_fighters_passes_womens_minimum() -> None:
    assert 9 >= min_pool_for_division("Women's Flyweight")
