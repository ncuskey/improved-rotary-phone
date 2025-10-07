import SwiftUI

struct StartScreenView: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @AppStorage("scanner.autoSubmit") private var autoSubmit = true
    @AppStorage("scanner.hapticsEnabled") private var hapticsEnabled = true

    @State private var isPresentingScanner = false
    @State private var scannedISBN: String?
    @State private var bookInfo: BookInfo?
    @State private var lastResult: BookInfo?

    // New state for networking and UI feedback
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(spacing: DS.Spacing.xl) {
            Text("Barcode Scanner")
                .titleStyle()
                .padding(.top, DS.Spacing.xl)

            Spacer()

            Button(action: {
                animate { errorMessage = nil }
                isPresentingScanner = true
            }) {
                Label(lastResult == nil ? "Scan ISBN" : "Scan Again", systemImage: "barcode.viewfinder")
                    .font(.title2.weight(.semibold))
                    .padding(.horizontal, DS.Spacing.xl)
                    .padding(.vertical, max(DS.Spacing.md, 12))
                    .background(DS.Color.primary)
                    .foregroundColor(.white)
                    .clipShape(Capsule())
            }
            .accessibilityIdentifier("scanISBNButton")
            .accessibilityLabel(lastResult == nil ? "Start scanning ISBN" : "Scan another ISBN")

            // Simulator-friendly test button to verify backend without camera
            Button(action: { performLookup(for: "9780670855032") }) {
                Text("Test Lookup (9780670855032)")
                    .bodyStyle()
                    .padding(.horizontal, DS.Spacing.xl)
                    .padding(.vertical, max(DS.Spacing.sm, 12))
                    .background(DS.Color.cardBg)
                    .clipShape(Capsule())
            }
            .accessibilityIdentifier("testLookupButton")
            .accessibilityLabel("Run test lookup for ISBN 9780670855032")

            if let isbn = scannedISBN, lastResult == nil {
                Text("Last scanned: \(isbn)")
                    .bodyStyle()
                    .foregroundStyle(DS.Color.textSecondary)
                    .padding(.top, DS.Spacing.sm)
            }

            if !autoSubmit, let pendingISBN = scannedISBN {
                Button {
                    performLookup(for: pendingISBN)
                } label: {
                    Label("Submit \(pendingISBN)", systemImage: "paperplane")
                        .font(.body.weight(.semibold))
                        .padding(.horizontal, DS.Spacing.xl)
                        .padding(.vertical, max(DS.Spacing.sm, 12))
                }
                .buttonStyle(.borderedProminent)
                .accessibilityLabel("Submit scanned ISBN \(pendingISBN)")
                .padding(.top, DS.Spacing.sm)
            }

            if isLoading {
                ProgressView("Looking up…")
                    .padding(.top, 4)
            }

            if let errorMessage = errorMessage {
                Text(errorMessage)
                    .foregroundColor(.red)
                    .font(.footnote)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)
            }

            if let info = bookInfo {
                VStack(spacing: DS.Spacing.md) {
                    if !info.thumbnail.isEmpty, let url = URL(string: info.thumbnail) {
                        AsyncImage(url: url) { image in
                            image
                                .resizable()
                                .aspectRatio(contentMode: .fit)
                        } placeholder: {
                            ProgressView()
                                .frame(width: 140, height: 180)
                        }
                        .frame(width: 140, height: 180)
                        .background(DS.Color.cardBg)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                        .shadow(color: DS.Shadow.card, radius: 10, x: 0, y: 6)
                    }

                    VStack(spacing: 6) {
                        Text(info.title)
                            .bodyStyle().fontWeight(.semibold)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal)

                        if let subtitle = info.subtitle, !subtitle.isEmpty {
                            Text(subtitle)
                                .subtitleStyle()
                                .multilineTextAlignment(.center)
                                .padding(.horizontal)
                        }

                        Text(info.author)
                            .subtitleStyle()
                            .multilineTextAlignment(.center)

                        if !info.additionalAuthors.isEmpty {
                            Text("Additional authors: \(info.additionalAuthors.joined(separator: ", "))")
                                .font(.caption)
                                .foregroundStyle(DS.Color.textSecondary)
                                .multilineTextAlignment(.center)
                                .padding(.horizontal)
                        }

                        if let year = info.publishedYear {
                            Text("Published: \(year)")
                                .font(.caption)
                                .foregroundStyle(DS.Color.textSecondary)
                        }

                        if !info.categories.isEmpty {
                            Text("Categories: \(info.categories.joined(separator: ", "))")
                                .font(.caption)
                                .foregroundStyle(DS.Color.textSecondary)
                                .multilineTextAlignment(.center)
                                .padding(.horizontal)
                        }

                        if let description = info.description, !description.isEmpty {
                            Text(description)
                                .font(.footnote)
                                .foregroundStyle(DS.Color.textPrimary)
                                .multilineTextAlignment(.center)
                                .lineLimit(5)
                                .padding(.horizontal)
                        }
                    }
                }
                .padding(.top, DS.Spacing.md)
                .padding()
                .background(DS.Color.cardBg)
                .clipShape(RoundedRectangle(cornerRadius: DS.Radius.md))
                .shadow(color: DS.Shadow.card, radius: 12, x: 0, y: 8)
                scanAgainButton
            }

            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.horizontal, DS.Spacing.xl)
        .background(DS.Color.background)
        .ignoresSafeArea(edges: .all)
        .fullScreenCover(isPresented: $isPresentingScanner) {
            ScannerModalView(onDismiss: { isPresentingScanner = false }, onCode: handleScan(code:))
        }
    }

    @MainActor
    private func performLookup(for isbn: String) {
        let trimmed = isbn.trimmingCharacters(in: .whitespacesAndNewlines)
        let digitsOnly = trimmed.filter { $0.isNumber }
        let query = digitsOnly.isEmpty ? trimmed : digitsOnly
        scannedISBN = query

        // Reset UI state and start loading
        isLoading = true
        animate {
            errorMessage = nil
            bookInfo = nil
        }

        BookAPI.fetchBookInfo(query) { result in
            DispatchQueue.main.async {
                self.isLoading = false
                if let info = result {
                    self.animate {
                        self.bookInfo = info
                        self.lastResult = info
                    }
                    if hapticsEnabled {
#if canImport(UIKit)
                        haptic(.success)
#endif
                    }
                } else {
                    self.animate {
                        self.errorMessage = "Lookup failed. Please check the server or ISBN and try again."
                    }
                    if hapticsEnabled {
#if canImport(UIKit)
                        haptic(.error)
#endif
                    }
                }
            }
        }
    }

    @MainActor
    private func handleScan(code: String) {
        let cleaned = code.filter { $0.isNumber }

        guard cleaned.count == 10 || cleaned.count == 13 else {
            animate {
                errorMessage = "That didn't look like a valid ISBN. Try again."
            }
            if hapticsEnabled {
#if canImport(UIKit)
                haptic(.error)
#endif
            }
            isPresentingScanner = false
            return
        }

        isPresentingScanner = false
        if autoSubmit {
            performLookup(for: cleaned)
        } else {
            animate {
                scannedISBN = cleaned
                errorMessage = nil
                bookInfo = nil
            }
            if hapticsEnabled {
#if canImport(UIKit)
                haptic(.success)
#endif
            }
        }
    }
}

private extension StartScreenView {
    func animate(_ changes: @escaping () -> Void) {
        if reduceMotion {
            changes()
        } else {
            withAnimation(.spring(response: 0.35, dampingFraction: 0.85)) {
                changes()
            }
        }
    }

    var scanAgainButton: some View {
        Button {
            animate { errorMessage = nil }
            isPresentingScanner = true
        } label: {
            Label("Scan another book", systemImage: "arrow.clockwise")
                .font(.footnote.weight(.semibold))
                .padding(.horizontal, DS.Spacing.xl)
                .padding(.vertical, max(DS.Spacing.sm, 12))
                .background(DS.Color.cardBg, in: Capsule())
        }
        .buttonStyle(.plain)
        .padding(.top, DS.Spacing.sm)
        .accessibilityLabel("Scan another book")
    }
}

#if canImport(UIKit)
import UIKit

struct ScannerModalView: View {
    var onDismiss: () -> Void
    var onCode: (String) -> Void

    @State private var isActive = true

    var body: some View {
        ZStack {
            BarcodeScannerView(isActive: $isActive, onScan: { code in
                onCode(code)
            })
                .ignoresSafeArea()

            Color.black.opacity(0.25)
                .ignoresSafeArea()
                .allowsHitTesting(false)

            VStack {
                HStack {
                    Spacer()
                    Button(action: {
                        isActive = false
                        onDismiss()
                    }) {
                        Image(systemName: "xmark.circle.fill")
                            .font(.system(size: 28, weight: .semibold))
                            .foregroundStyle(.white)
                            .shadow(radius: 4)
                    }
                }
                .padding([.top, .horizontal], DS.Spacing.xl)

                Spacer()

                PulsingReticle()
                    .allowsHitTesting(false)

                Text("Align the barcode within the frame")
                    .font(.callout)
                    .foregroundStyle(.white.opacity(0.9))
                    .padding(.top, DS.Spacing.sm)

                Text("Hold steady—scanning is automatic.")
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.7))

                Spacer()

                Button(action: {
                    isActive = false
                    onDismiss()
                }) {
                    Label("Cancel Scan", systemImage: "xmark")
                        .font(.body.weight(.semibold))
                        .padding(.horizontal, DS.Spacing.xl)
                        .padding(.vertical, DS.Spacing.sm)
                        .background(.ultraThinMaterial, in: Capsule())
                        .foregroundColor(.white)
                }
                .padding(.bottom, DS.Spacing.xl)
            }
        }
        .onAppear { isActive = true }
        .onDisappear { isActive = false }
    }
}

struct PulsingReticle: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pulse = false

    var body: some View {
        RoundedRectangle(cornerRadius: 22)
            .stroke(Color.white.opacity(0.85), lineWidth: 3)
            .frame(width: 240, height: 240)
            .overlay(
                RoundedRectangle(cornerRadius: 26)
                    .stroke(Color.white.opacity(0.35), lineWidth: 3)
                    .scaleEffect(pulse ? 1.08 : 0.92)
                    .opacity(pulse ? 0 : 1)
            )
            .padding(.vertical, DS.Spacing.lg)
            .onAppear {
                guard !reduceMotion else { return }
                pulse = true
            }
            .animation(reduceMotion ? nil : .easeInOut(duration: 1.5).repeatForever(autoreverses: true), value: pulse)
    }
}

func haptic(_ type: UINotificationFeedbackGenerator.FeedbackType) {
    let generator = UINotificationFeedbackGenerator()
    generator.notificationOccurred(type)
}

#else
struct ScannerModalView: View {
    var onDismiss: () -> Void
    var onCode: (String) -> Void

    var body: some View {
        VStack(spacing: DS.Spacing.md) {
            Text("Scanning not supported on this platform.")
                .bodyStyle()
            Button("Close", action: onDismiss)
        }
        .padding()
    }
}
#endif

#Preview {
    StartScreenView()
}
