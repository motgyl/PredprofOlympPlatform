def calculate_elo(winner_elo, loser_elo):
    """
    Расчет изменения рейтинга по системе ELO.
    K-factor = 32 (коэффициент изменений)
    """
    K = 32
    
    # Вероятность выигрыша для каждого игрока
    prob_winner = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
    prob_loser = 1 / (1 + 10 ** ((winner_elo - loser_elo) / 400))
    
    # Новые рейтинги
    new_winner_elo = winner_elo + K * (1 - prob_winner)
    new_loser_elo = loser_elo + K * (0 - prob_loser)
    
    return int(new_winner_elo), int(new_loser_elo)

def calculate_elo_result(p1_elo, p2_elo, result_p1):
    """
    Универсальный расчет ELO по результату матча.
    result_p1: 1.0 (победа p1), 0.5 (ничья), 0.0 (поражение p1)
    """
    K = 32
    expected_p1 = 1 / (1 + 10 ** ((p2_elo - p1_elo) / 400))
    expected_p2 = 1 / (1 + 10 ** ((p1_elo - p2_elo) / 400))
    new_p1 = p1_elo + K * (result_p1 - expected_p1)
    new_p2 = p2_elo + K * ((1 - result_p1) - expected_p2)
    return int(new_p1), int(new_p2)
