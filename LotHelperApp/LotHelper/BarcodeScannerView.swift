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
#endif

#if canImport(UIKit)
class ScannerViewController: UIViewController, AVCaptureMetadataOutputObjectsDelegate {
    var captureSession: AVCaptureSession?
    var previewLayer: AVCaptureVideoPreviewLayer?
    var lastScannedCode: String?
    var lastScanTime = Date(timeIntervalSince1970: 0)
    var onScan: ((String) -> Void)?

    override func viewDidLoad() {
        super.viewDidLoad()
        checkCameraAuthorization()
    }

    private func checkCameraAuthorization() {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            setupSession()
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
                DispatchQueue.main.async {
                    if granted {
                        self?.setupSession()
                    } else {
                        self?.showCameraDeniedUI()
                    }
                }
            }
        case .denied, .restricted:
            showCameraDeniedUI()
        @unknown default:
            showCameraDeniedUI()
        }
    }

    private func setupSession() {
        let session = AVCaptureSession()

        guard let videoCaptureDevice = AVCaptureDevice.default(for: .video) else {
            showUnsupportedUI()
            return
        }

        guard let videoInput = try? AVCaptureDeviceInput(device: videoCaptureDevice),
              session.canAddInput(videoInput) else {
            showUnsupportedUI()
            return
        }
        session.addInput(videoInput)

        let metadataOutput = AVCaptureMetadataOutput()
        guard session.canAddOutput(metadataOutput) else {
            showUnsupportedUI()
            return
        }
        session.addOutput(metadataOutput)

        metadataOutput.setMetadataObjectsDelegate(self, queue: DispatchQueue.main)

        // Filter desired types by what the device actually supports to avoid configuration errors
        let desired: [AVMetadataObject.ObjectType] = [.ean8, .ean13, .pdf417, .qr]
        let supported = Set(metadataOutput.availableMetadataObjectTypes)
        metadataOutput.metadataObjectTypes = desired.filter { supported.contains($0) }

        let preview = AVCaptureVideoPreviewLayer(session: session)
        preview.frame = view.layer.bounds
        preview.videoGravity = .resizeAspectFill
        view.layer.addSublayer(preview)

        self.captureSession = session
        self.previewLayer = preview
        session.startRunning()
    }

    private func showCameraDeniedUI() {
        let label = UILabel()
        label.text = "Camera access is required to scan barcodes. Enable it in Settings."
        label.textAlignment = .center
        label.numberOfLines = 0
        label.textColor = .secondaryLabel
        label.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(label)
        NSLayoutConstraint.activate([
            label.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            label.centerYAnchor.constraint(equalTo: view.centerYAnchor),
            label.leadingAnchor.constraint(greaterThanOrEqualTo: view.leadingAnchor, constant: 20),
            label.trailingAnchor.constraint(lessThanOrEqualTo: view.trailingAnchor, constant: -20)
        ])
    }

    private func showUnsupportedUI() {
        let label = UILabel()
        label.text = "This device does not support barcode scanning."
        label.textAlignment = .center
        label.numberOfLines = 0
        label.textColor = .secondaryLabel
        label.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(label)
        NSLayoutConstraint.activate([
            label.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            label.centerYAnchor.constraint(equalTo: view.centerYAnchor),
            label.leadingAnchor.constraint(greaterThanOrEqualTo: view.leadingAnchor, constant: 20),
            label.trailingAnchor.constraint(lessThanOrEqualTo: view.trailingAnchor, constant: -20)
        ])
    }

    func metadataOutput(_ output: AVCaptureMetadataOutput,
                        didOutput metadataObjects: [AVMetadataObject],
                        from connection: AVCaptureConnection) {
        guard let metadataObject = metadataObjects.first,
              let readableObject = metadataObject as? AVMetadataMachineReadableCodeObject,
              let stringValue = readableObject.stringValue else { return }

        // Debounce logic: Ignore duplicates scanned within 2 seconds
        if stringValue == lastScannedCode && Date().timeIntervalSince(lastScanTime) < 2 {
            return
        }

        lastScannedCode = stringValue
        lastScanTime = Date()

        onScan?(stringValue)
        captureSession?.stopRunning()

        print("🔍 Scanned code: \(stringValue)")
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        previewLayer?.frame = view.layer.bounds
    }

    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        if captureSession?.isRunning == true {
            captureSession?.stopRunning()
        }
    }
}

struct BarcodeScannerView: UIViewControllerRepresentable {
    var onScan: (String) -> Void = { _ in }

    func makeUIViewController(context: Context) -> ScannerViewController {
        let controller = ScannerViewController()
        controller.onScan = onScan
        return controller
    }

    func updateUIViewController(_ uiViewController: ScannerViewController, context: Context) {}
}
#else
struct BarcodeScannerView: View {
    var onScan: (String) -> Void = { _ in }
    var body: some View {
        Text("Barcode scanning is not supported on this platform.")
            .foregroundStyle(DS.Color.textSecondary)
    }
}
#endif
