import AudioToolbox
import UIKit

/// Provides audio and haptic feedback for app actions
enum SoundFeedback {
    /// Play sound when barcode is detected
    static func scanDetected() {
        AudioServicesPlaySystemSound(1054) // Tock - subtle
    }

    /// Play sound when book is successfully added
    static func success() {
        AudioServicesPlaySystemSound(1057) // Payment Success
    }

    /// Play sound when an error occurs
    static func error() {
        AudioServicesPlaySystemSound(1053) // Access Denied
    }

    /// Play sound when book is rejected/deleted
    static func reject() {
        AudioServicesPlaySystemSound(1072) // Low Power
    }

    /// Provide haptic feedback
    static func haptic(_ type: UINotificationFeedbackGenerator.FeedbackType) {
        let generator = UINotificationFeedbackGenerator()
        generator.notificationOccurred(type)
    }

    /// Light impact haptic (for UI interactions)
    static func lightImpact() {
        let generator = UIImpactFeedbackGenerator(style: .light)
        generator.impactOccurred()
    }

    /// Medium impact haptic (for button presses)
    static func mediumImpact() {
        let generator = UIImpactFeedbackGenerator(style: .medium)
        generator.impactOccurred()
    }
}
