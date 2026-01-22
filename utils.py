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