func updateProbability(data: [String: Any]) -> Double {
    let result = calculateScore(data)
    return result