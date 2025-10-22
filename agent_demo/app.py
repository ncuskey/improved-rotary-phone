def get_probability(score):
    # Updated probability scoring method to match main.swift
    if score < 0:
        return 0
    elif score > 1:
        return 1
    else:
        return score