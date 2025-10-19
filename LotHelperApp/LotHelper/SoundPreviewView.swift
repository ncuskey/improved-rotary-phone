import SwiftUI
import AudioToolbox

struct SoundPreviewView: View {
    let sounds: [(id: SystemSoundID, name: String, category: String)] = [
        // Success sounds
        (1057, "Payment Success", "Success"),
        (1054, "Tock", "Success"),
        (1304, "Note", "Success"),
        (1315, "Anticipate", "Success"),

        // Scanning sounds
        (1103, "SMS Received", "Scan"),
        (1106, "Text Tone", "Scan"),
        (1050, "New Mail", "Scan"),
        (1104, "Sent Message", "Scan"),

        // Error sounds
        (1053, "Access Denied", "Error"),
        (1072, "Low Power", "Error"),

        // Camera
        (1108, "Camera Shutter", "Camera"),
    ]

    var body: some View {
        NavigationStack {
            List {
                ForEach(["Success", "Scan", "Error", "Camera"], id: \.self) { category in
                    Section(category) {
                        ForEach(sounds.filter { $0.category == category }, id: \.id) { sound in
                            Button(action: {
                                AudioServicesPlaySystemSound(sound.id)
                            }) {
                                HStack {
                                    Text(sound.name)
                                        .foregroundStyle(.primary)
                                    Spacer()
                                    Image(systemName: "speaker.wave.2.fill")
                                        .foregroundStyle(.blue)
                                        .font(.caption)
                                }
                            }
                        }
                    }
                }

                Section("Haptics (No Sound)") {
                    Button("Success Haptic") {
                        let generator = UINotificationFeedbackGenerator()
                        generator.notificationOccurred(.success)
                    }
                    Button("Warning Haptic") {
                        let generator = UINotificationFeedbackGenerator()
                        generator.notificationOccurred(.warning)
                    }
                    Button("Error Haptic") {
                        let generator = UINotificationFeedbackGenerator()
                        generator.notificationOccurred(.error)
                    }
                    Button("Light Impact") {
                        let generator = UIImpactFeedbackGenerator(style: .light)
                        generator.impactOccurred()
                    }
                    Button("Medium Impact") {
                        let generator = UIImpactFeedbackGenerator(style: .medium)
                        generator.impactOccurred()
                    }
                    Button("Heavy Impact") {
                        let generator = UIImpactFeedbackGenerator(style: .heavy)
                        generator.impactOccurred()
                    }
                }
            }
            .navigationTitle("Sound Preview")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

#Preview {
    SoundPreviewView()
}
