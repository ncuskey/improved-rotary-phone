//
//  Item.swift
//  LotHelper
//
//  Created by Nicholas Cuskey on 10/3/25.
//

import Foundation
import SwiftData

@Model
final class Item {
    var timestamp: Date
    
    init(timestamp: Date) {
        self.timestamp = timestamp
    }
}
