

def implied_probability(odds: int, round_n=4) -> float:
    """Given the odds of a bet, calculate the implied probability

    Args:
        odds (int): odds of the bet (american so 200 would correspond to a 2/1 bet with 33% implied prob). will convert strings to ints
        round_n (int, optional): precision of decimal probability. Defaults to 2.

    Returns:
        float: implied probability of the bet
    """
    try:
        odds = int(odds)
    except ValueError:
        print("Invalid odds in betting-utils.py/implied_probability()")

    assert abs(odds) >= 100, 'error odds are <100 cannot calculate prob'
    if odds < 0:
        return round(odds / (odds - 100), round_n)
    else:
        return round(1 - (odds / (odds + 100)), round_n)


def odds(implied_prob: float, as_str=False):
    """Given an implied probability calculate the american odds

    Args:
        implied_prob (float): implied probability of the bet
        as_str (bool, optional): will format value as a string and return positive odds with the '+'. Defaults to False.

    Returns:
        int: american odds of the event, ex: .5 will return 100. '
    """
    # favored event, odds will be negative
    if implied_prob > 0.5:
        res_odds = int((100 * implied_prob) / (implied_prob - 1))
        return f'{res_odds}' if as_str else res_odds
    # underdog event, odds will be positive
    else:
        res_odds = int((100 - 100 * implied_prob) / implied_prob)
        return f'+{res_odds}' if as_str else res_odds

def decimal_odds(implied_prob: float) -> float:
    return 1/ implied_prob

def decimal_implied_probability(decimal_odds: float) -> float:
    return 1 / decimal_odds

def decimal_odds_to_american(decimal_odds: float) -> int:
    if decimal_odds >= 2.0:
        american_odds = (decimal_odds - 1) * 100
    else:
        american_odds = -100 / (decimal_odds - 1)
    return round(american_odds)