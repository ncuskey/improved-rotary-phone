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

final class ScannerViewController: UIViewController, AVCaptureMetadataOutputObjectsDelegate {
    var onScan: ((String) -> Void)?

    private let session = AVCaptureSession()
    private var previewLayer: AVCaptureVideoPreviewLayer?
    private var isSessionConfigured = false
    private var isActive = true
    private let sessionQueue = DispatchQueue(label: "com.lothelper.scanner.session")

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

        let output = AVCaptureMetadataOutput()
        guard session.canAddOutput(output) else {
            showCameraUnavailableUI()
            session.commitConfiguration()
            return
        }
        session.addOutput(output)
        output.metadataObjectTypes = [.ean13, .ean8, .upce, .code128, .qr]
        output.setMetadataObjectsDelegate(self, queue: DispatchQueue.main)

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

    // MARK: - Metadata delegate

    func metadataOutput(_ output: AVCaptureMetadataOutput,
                        didOutput metadataObjects: [AVMetadataObject],
                        from connection: AVCaptureConnection) {
        guard isActive,
              let object = metadataObjects.first as? AVMetadataMachineReadableCodeObject,
              let value = object.stringValue, !value.isEmpty else { return }

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
            .foregroundStyle(DS.Color.textSecondary)
    }
}
#endif
