// oracle.swift — build and run to print expected outputs as JSON
import Foundation

func probabilityScore(_ x: Double) -> Double {
    // TODO: REPLACE with your real iOS method body copied from your app
    // Example placeholder:
    let clamped = max(0.0, min(1.0, x))
    return 0.2 + 0.6 * clamped
}

let inputs: [Double] = [0, 0.1, 0.5, 0.9, 1.0]
let outputs = inputs.map { probabilityScore($0) }
let dict: [String: Double] = Dictionary(uniqueKeysWithValues: zip(inputs.map{String($0)}, outputs))
if let data = try? JSONSerialization.data(withJSONObject: dict, options: [.sortedKeys]) {
    print(String(data: data, encoding: .utf8)!)
}
