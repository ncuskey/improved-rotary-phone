//
//  BarcodeScannerView.swift
//  LotHelper
//
//  Created by Nicholas Cuskey on 10/3/25.
//

import SwiftUI

#if canImport(UIKit)
import UIKit
import AVFoundation
import AudioToolbox
import Vision

struct BarcodeScannerView: UIViewControllerRepresentable {
    @Binding var isActive: Bool
    var onScan: (String) -> Void

    func makeUIViewController(context: Context) -> ScannerViewController {
        let controller = ScannerViewController()
        controller.onScan = onScan
        controller.setActive(isActive)
        return controller
    }

    func updateUIViewController(_ uiViewController: ScannerViewController, context: Context) {
        uiViewController.onScan = onScan
        uiViewController.setActive(isActive)
    }
}

final class ScannerViewController: UIViewController, AVCaptureMetadataOutputObjectsDelegate, AVCaptureVideoDataOutputSampleBufferDelegate {
    var onScan: ((String) -> Void)?

    private let session = AVCaptureSession()
    private var previewLayer: AVCaptureVideoPreviewLayer?
    private var isSessionConfigured = false
    private var isActive = true
    private let sessionQueue = DispatchQueue(label: "com.lothelper.scanner.session")
    private let visionQueue = DispatchQueue(label: "com.lothelper.scanner.vision")
    private var lastOCRAttempt = Date.distantPast

    // Candidate accumulation
    private var candidateISBNs: Set<String> = []
    private var scanStartTime = Date()
    private var hasScannedBarcode = false

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        configureIfNeeded()

        let tap = UITapGestureRecognizer(target: self, action: #selector(handleTap(_:)))
        view.addGestureRecognizer(tap)
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        previewLayer?.frame = view.bounds
    }

    func setActive(_ active: Bool) {
        guard isActive != active else { return }
        isActive = active
        if active {
            startSessionIfPossible()
        } else {
            sessionQueue.async { [weak self] in
                guard let self else { return }
                if self.session.isRunning {
                    self.session.stopRunning()
                }
            }
        }
    }

    private func configureIfNeeded() {
        guard !isSessionConfigured else { return }
        isSessionConfigured = true

        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            setupSession()
            startSessionIfPossible()
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
                DispatchQueue.main.async {
                    guard let self else { return }
                    if granted {
                        self.setupSession()
                        self.startSessionIfPossible()
                    } else {
                        self.showPermissionDeniedUI()
                    }
                }
            }
        case .denied, .restricted:
            showPermissionDeniedUI()
        @unknown default:
            showPermissionDeniedUI()
        }
    }

    private func setupSession() {
        session.beginConfiguration()
        session.sessionPreset = .high

        guard let device = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
              let input = try? AVCaptureDeviceInput(device: device),
              session.canAddInput(input) else {
            showCameraUnavailableUI()
            session.commitConfiguration()
            return
        }
        session.addInput(input)

        // Barcode metadata output
        let metadataOutput = AVCaptureMetadataOutput()
        guard session.canAddOutput(metadataOutput) else {
            showCameraUnavailableUI()
            session.commitConfiguration()
            return
        }
        session.addOutput(metadataOutput)
        metadataOutput.metadataObjectTypes = [.ean13, .ean8, .upce, .code128, .qr]
        metadataOutput.setMetadataObjectsDelegate(self, queue: DispatchQueue.main)

        // Video data output for OCR text recognition
        let videoOutput = AVCaptureVideoDataOutput()
        videoOutput.setSampleBufferDelegate(self, queue: visionQueue)
        videoOutput.alwaysDiscardsLateVideoFrames = true
        if session.canAddOutput(videoOutput) {
            session.addOutput(videoOutput)
        }

        let layer = AVCaptureVideoPreviewLayer(session: session)
        layer.videoGravity = .resizeAspectFill
        view.layer.addSublayer(layer)
        previewLayer = layer

        session.commitConfiguration()
    }

    private func startSessionIfPossible() {
        guard isActive, isSessionConfigured else { return }
        sessionQueue.async { [weak self] in
            guard let self else { return }
            if !self.session.isRunning {
                self.session.startRunning()
            }
        }
    }

    // MARK: - Metadata delegate (Barcode)

    func metadataOutput(_ output: AVCaptureMetadataOutput,
                        didOutput metadataObjects: [AVMetadataObject],
                        from connection: AVCaptureConnection) {
        guard isActive,
              let object = metadataObjects.first as? AVMetadataMachineReadableCodeObject,
              let value = object.stringValue, !value.isEmpty else { return }

        hasScannedBarcode = true

        // Add to candidates if valid ISBN
        if isValidISBNFormat(value) {
#if DEBUG
            print("📷 Barcode found valid ISBN: \(value)")
#endif
            addCandidate(value, source: "barcode")
        } else {
#if DEBUG
            print("📷 Barcode rejected non-ISBN: \(value) (length: \(value.count))")
#endif
        }

        // Check if we should evaluate candidates
        checkAndSelectBestCandidate()
    }

    // MARK: - Video data delegate (OCR)

    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        // Throttle OCR attempts to every 0.2 seconds for faster detection
        guard isActive, Date().timeIntervalSince(lastOCRAttempt) > 0.2 else { return }
        lastOCRAttempt = Date()

        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }

        let request = VNRecognizeTextRequest { [weak self] request, error in
            guard let self else { return }

            if let error = error {
                #if DEBUG
                print("OCR Error: \(error)")
                #endif
                return
            }

            guard let observations = request.results as? [VNRecognizedTextObservation] else { return }

            #if DEBUG
            if !observations.isEmpty {
                print("OCR found \(observations.count) text regions")
                for (idx, obs) in observations.prefix(5).enumerated() {
                    if let candidate = obs.topCandidates(1).first {
                        print("  [\(idx)] \(candidate.string) (confidence: \(candidate.confidence))")
                    }
                }
            }
            #endif

            self.processOCRResults(observations)
        }

        // Use accurate recognition for better ISBN detection
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        request.recognitionLanguages = ["en-US"]
        request.minimumTextHeight = 0.03  // Smaller text detection

        let handler = VNImageRequestHandler(cvPixelBuffer: pixelBuffer, orientation: .up, options: [:])
        try? handler.perform([request])
    }

    private func processOCRResults(_ observations: [VNRecognizedTextObservation]) {
        // Look for ISBN patterns in recognized text (with or without dashes/spaces)
        let isbnPattern = #"(?:ISBN[:\s-]?)?([0-9Xx][\s-]?[0-9Xx][\s-]?[0-9Xx][\s-]?[0-9Xx][\s-]?[0-9Xx][\s-]?[0-9Xx][\s-]?[0-9Xx][\s-]?[0-9Xx][\s-]?[0-9Xx][\s-]?[0-9Xx](?:[\s-]?[0-9Xx][\s-]?[0-9Xx][\s-]?[0-9Xx])?)"#

        let regex = try? NSRegularExpression(pattern: isbnPattern, options: [.caseInsensitive])

        for observation in observations {
            guard let candidate = observation.topCandidates(1).first else { continue }
            let text = candidate.string

            // Try to find ISBN in the text
            let range = NSRange(text.startIndex..<text.endIndex, in: text)
            if let match = regex?.firstMatch(in: text, range: range),
               let isbnRange = Range(match.range(at: 1), in: text) {
                let rawISBN = String(text[isbnRange])

                // Remove dashes and spaces to get clean ISBN
                let cleanISBN = rawISBN.replacingOccurrences(of: "-", with: "")
                                       .replacingOccurrences(of: " ", with: "")
                                       .uppercased()

                #if DEBUG
                print("Found potential ISBN: '\(rawISBN)' -> '\(cleanISBN)'")
                #endif

                if isValidISBNFormat(cleanISBN) {
                    #if DEBUG
                    print("📝 OCR found valid ISBN: \(cleanISBN)")
                    #endif
                    DispatchQueue.main.async { [weak self] in
                        guard let self, self.isActive else { return }
                        self.addCandidate(cleanISBN, source: "OCR")
                        self.checkAndSelectBestCandidate()
                    }
                    return
                } else {
                    #if DEBUG
                    print("❌ Invalid ISBN format: \(cleanISBN)")
                    #endif
                }
            }
        }
    }

    // MARK: - Candidate Management

    private func addCandidate(_ isbn: String, source: String) {
        candidateISBNs.insert(isbn)
#if DEBUG
        print("  Added candidate from \(source): \(isbn) (total: \(candidateISBNs.count))")
#endif
    }

    private func checkAndSelectBestCandidate() {
        let elapsed = Date().timeIntervalSince(scanStartTime)

        // Wait for both barcode and OCR to have a chance (1 second window)
        // OR if we already have an ISBN from OCR after barcode failed
        let shouldSelect = elapsed > 1.0 || (hasScannedBarcode && !candidateISBNs.isEmpty)

        if shouldSelect && !candidateISBNs.isEmpty {
            selectBestCandidate()
        }
    }

    private func selectBestCandidate() {
        guard !candidateISBNs.isEmpty else { return }

        // Prefer ISBN-13 over ISBN-10 (more specific)
        let isbn13s = candidateISBNs.filter { $0.count == 13 }
        let isbn10s = candidateISBNs.filter { $0.count == 10 }

        let bestISBN: String
        if !isbn13s.isEmpty {
            bestISBN = isbn13s.first!
        } else {
            bestISBN = isbn10s.first!
        }

#if DEBUG
        print("🎯 Selected best ISBN: \(bestISBN) from \(candidateISBNs.count) candidate(s)")
        print("   All candidates: \(candidateISBNs.sorted())")
#endif

        handleSuccessfulScan(bestISBN)
    }

    // MARK: - ISBN Validation

    private func isValidISBNFormat(_ isbn: String) -> Bool {
        // ISBN-10: 9 digits + check digit (0-9 or X)
        if isbn.count == 10 {
            let digits = isbn.prefix(9)
            let check = isbn.suffix(1)
            return digits.allSatisfy { $0.isNumber } && (check.first?.isNumber == true || check == "X")
        }
        // ISBN-13: 13 digits
        if isbn.count == 13 {
            return isbn.allSatisfy { $0.isNumber }
        }
        return false
    }

    private func handleSuccessfulScan(_ value: String) {
        guard isActive else { return }

        isActive = false
        sessionQueue.async { [weak self] in
            guard let self else { return }
            if self.session.isRunning {
                self.session.stopRunning()
            }
        }

        AudioServicesPlaySystemSound(kSystemSoundID_Vibrate)
        onScan?(value)
    }

    // MARK: - Fallback UIs

    private func showPermissionDeniedUI() {
        let label = makeLabel(text: "Camera permission denied.\nEnable access in Settings to scan barcodes.")
        view.addSubview(label)
        constrain(label)
    }

    private func showCameraUnavailableUI() {
        let label = makeLabel(text: "Camera unavailable on this device.")
        view.addSubview(label)
        constrain(label)
    }

    private func makeLabel(text: String) -> UILabel {
        let label = UILabel()
        label.text = text
        label.numberOfLines = 0
        label.textAlignment = .center
        label.textColor = .secondaryLabel
        label.translatesAutoresizingMaskIntoConstraints = false
        return label
    }

    private func constrain(_ label: UILabel) {
        NSLayoutConstraint.activate([
            label.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            label.centerYAnchor.constraint(equalTo: view.centerYAnchor),
            label.leadingAnchor.constraint(greaterThanOrEqualTo: view.leadingAnchor, constant: 20),
            label.trailingAnchor.constraint(lessThanOrEqualTo: view.trailingAnchor, constant: -20)
        ])
    }

    // MARK: - Tap to focus

    @objc private func handleTap(_ recognizer: UITapGestureRecognizer) {
        let location = recognizer.location(in: view)
        guard let layer = previewLayer,
              let input = session.inputs.first as? AVCaptureDeviceInput else { return }

        let devicePoint = layer.captureDevicePointConverted(fromLayerPoint: location)
        let device = input.device

        do {
            try device.lockForConfiguration()

            if device.isFocusPointOfInterestSupported {
                device.focusPointOfInterest = devicePoint
                if device.isFocusModeSupported(.autoFocus) {
                    device.focusMode = .autoFocus
                }
            }

            if device.isExposurePointOfInterestSupported {
                device.exposurePointOfInterest = devicePoint
                if device.isExposureModeSupported(.continuousAutoExposure) {
                    device.exposureMode = .continuousAutoExposure
                }
            }

            device.unlockForConfiguration()
        } catch {
            #if DEBUG
            print("Focus configuration failed: \(error)")
            #endif
        }
    }
}
#else
struct BarcodeScannerView: View {
    @Binding var isActive: Bool
    var onScan: (String) -> Void = { _ in }
    var body: some View {
        Text("Barcode scanning is not supported on this platform.")
            .foregroundStyle(.secondary)
    }
}
#endif
