from flask import Flask, request, jsonify

app = Flask(__name__)

def calculate_score(data):
    """
    Calculates a probability score for an ISBN-13 based on its checksum.
    The logic is ported from the LotHelperApp's calculateScore function.
    Returns 1.0 for a valid ISBN-13, 0.0 otherwise.
    """
    if not data or 'isbn' not in data or not isinstance(data['isbn'], str):
        return 0.0

    isbn = data['isbn'].replace('-', '').replace(' ', '')

    if len(isbn) != 13 or not isbn.isdigit():
        return 0.0

    digits = [int(d) for d in isbn]
    
    # ISBN-13 checksum calculation:
    # Sum of the first 12 digits, with weights alternating 1 and 3.
    # The total sum (including the 13th check digit) must be divisible by 10.
    checksum = sum(d * (1 if i % 2 == 0 else 3) for i, d in enumerate(digits[:-1]))
    
    if (checksum + digits[-1]) % 10 == 0:
        return 1.0
    else:
        return 0.0

@app.route('/calculate-score', methods=['POST'])
def update_probability():
    """
    An endpoint to calculate the probability score of an ISBN.
    This API is a port of the Swift updateProbability function.
    """
    if not request.is_json:
        return jsonify({"error": "Invalid input, JSON required"}), 400
    
    data = request.get_json()
    score = calculate_score(data)
    return jsonify({"score": score})


@app.route('/isbn-check', methods=['POST'])
def check_isbn():
    data = request.get_json()
    if not data or 'isbn' not in data:
        return jsonify({'error': 'Missing ISBN'}), 400

    # Dummy check
    is_valid = len(data['isbn']) > 0

    return jsonify({'valid': is_valid})

if __name__ == '__main__':
    app.run(port=5001, debug=True)