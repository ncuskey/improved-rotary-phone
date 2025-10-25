//
//  LocationManager.swift
//  LotHelper
//
//  Manages location tracking for scan history
//

import SwiftUI
import CoreLocation
import MapKit
import Combine

@MainActor
class LocationManager: NSObject, ObservableObject {
    private let manager = CLLocationManager()

    @Published var currentLocation: CLLocation?
    @Published var currentLocationName: String?
    @Published var authorizationStatus: CLAuthorizationStatus = .notDetermined
    @Published var isUpdatingLocation = false

    // Cached location info (persists between scans)
    @AppStorage("lastLocationName") private var lastLocationName: String?
    @AppStorage("lastLocationLatitude") private var lastLocationLatitude: Double?
    @AppStorage("lastLocationLongitude") private var lastLocationLongitude: Double?

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
        manager.distanceFilter = 100 // Only update if moved 100m
        authorizationStatus = manager.authorizationStatus
    }

    func requestLocationPermission() {
        print("📍 LocationManager: Requesting When In Use authorization...")
        print("📍 Current status: \(manager.authorizationStatus.rawValue)")
        manager.requestWhenInUseAuthorization()
    }

    func requestLocation() {
        guard authorizationStatus == .authorizedWhenInUse || authorizationStatus == .authorizedAlways else {
            print("⚠️ Location not authorized")
            return
        }

        isUpdatingLocation = true
        manager.requestLocation()
    }

    func startUpdatingLocation() {
        guard authorizationStatus == .authorizedWhenInUse || authorizationStatus == .authorizedAlways else {
            return
        }

        manager.startUpdatingLocation()
    }

    func stopUpdatingLocation() {
        manager.stopUpdatingLocation()
        isUpdatingLocation = false
    }

    private func reverseGeocode(location: CLLocation) {
        // Use CLGeocoder for broad OS compatibility
        let geocoder = CLGeocoder()
        geocoder.reverseGeocodeLocation(location) { [weak self] placemarks, error in
            guard let self = self else { return }

            if let error = error {
                print("⚠️ Geocoding error: \(error.localizedDescription)")
                Task { @MainActor in
                    self.currentLocationName = "Unknown Location"
                }
                return
            }

            guard let placemark = placemarks?.first else {
                Task { @MainActor in
                    self.currentLocationName = "Unknown Location"
                }
                return
            }

            Task { @MainActor in
                // Build a nice location name
                var components: [String] = []

                // Try to get business name first
                if let name = placemark.name, !name.isEmpty {
                    components.append(name)
                }

                // Add thoroughfare (street) if available and not already in name
                if let thoroughfare = placemark.thoroughfare,
                   !components.contains(where: { $0.contains(thoroughfare) }) {
                    if let subThoroughfare = placemark.subThoroughfare {
                        components.append("\(subThoroughfare) \(thoroughfare)")
                    } else {
                        components.append(thoroughfare)
                    }
                }

                // Add locality (city)
                if let locality = placemark.locality {
                    components.append(locality)
                }

                let locationName = components.isEmpty ? "Unknown Location" : components.joined(separator: ", ")
                self.currentLocationName = locationName

                // Cache for next scan
                self.lastLocationName = locationName
                self.lastLocationLatitude = location.coordinate.latitude
                self.lastLocationLongitude = location.coordinate.longitude

                print("📍 Location: \(locationName)")
            }
        }
    }

    // Get current location data for API calls
    var locationData: (name: String?, latitude: Double?, longitude: Double?, accuracy: Double?) {
        if let location = currentLocation {
            return (
                name: currentLocationName ?? lastLocationName,
                latitude: location.coordinate.latitude,
                longitude: location.coordinate.longitude,
                accuracy: location.horizontalAccuracy
            )
        } else if let lat = lastLocationLatitude, let lon = lastLocationLongitude {
            // Use cached location if current location not available
            return (
                name: lastLocationName,
                latitude: lat,
                longitude: lon,
                accuracy: nil
            )
        }

        return (name: nil, latitude: nil, longitude: nil, accuracy: nil)
    }
}

extension LocationManager: CLLocationManagerDelegate {
    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        Task { @MainActor in
            authorizationStatus = manager.authorizationStatus

            switch authorizationStatus {
            case .authorizedWhenInUse, .authorizedAlways:
                print("✓ Location authorized")
                requestLocation()
            case .denied, .restricted:
                print("⚠️ Location access denied")
            case .notDetermined:
                print("ℹ️ Location authorization not determined")
            @unknown default:
                break
            }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let location = locations.last else { return }

        Task { @MainActor in
            currentLocation = location
            isUpdatingLocation = false

            print("📍 Got location: \(location.coordinate.latitude), \(location.coordinate.longitude)")

            // Reverse geocode to get place name
            reverseGeocode(location: location)
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        Task { @MainActor in
            isUpdatingLocation = false
            print("⚠️ Location error: \(error.localizedDescription)")

            // Use cached location if available
            if lastLocationName != nil {
                currentLocationName = lastLocationName
                print("ℹ️ Using cached location: \(lastLocationName ?? "unknown")")
            }
        }
    }
}

