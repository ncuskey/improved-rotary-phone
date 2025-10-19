import AudioToolbox
import AVFoundation
import UIKit

/// Provides audio and haptic feedback for app actions
enum SoundFeedback {
    private static var audioPlayer: AVAudioPlayer?

    /// Play sound when barcode is detected
    static func scanDetected() {
        AudioServicesPlaySystemSound(1057) // Tink - subtle confirmation
    }

    /// Play sound when book is successfully added
    static func success() {
        AudioServicesPlaySystemSound(1054) // Success sound
    }

    /// Play sound when an error occurs
    static func error() {
        AudioServicesPlaySystemSound(1053) // Access Denied
    }

    /// Play sound when book is rejected/deleted
    static func reject() {
        AudioServicesPlaySystemSound(1072) // Low Power
    }

    /// Play sound when recommendation is BUY
    static func buyRecommendation() {
        // Use custom cash register sound
        guard let soundURL = Bundle.main.url(forResource: "Cha-Ching", withExtension: "mp3") else {
            print("⚠️ Could not find Cha-Ching.mp3, falling back to system sound")
            AudioServicesPlaySystemSound(1054)
            return
        }

        do {
            audioPlayer = try AVAudioPlayer(contentsOf: soundURL)
            audioPlayer?.play()
        } catch {
            print("⚠️ Could not play custom sound: \(error), falling back to system sound")
            AudioServicesPlaySystemSound(1054)
        }
    }

    /// Play sound when recommendation is DON'T BUY
    static func dontBuyRecommendation() {
        AudioServicesPlaySystemSound(1053) // Access Denied (rejection)
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
