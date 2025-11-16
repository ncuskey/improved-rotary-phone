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
import Contacts

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
        // Use MKLocalSearch for reverse geocoding (modern MapKit approach)
        // This avoids CLGeocoder deprecation warnings while maintaining compatibility
        Task {
            do {
                let request = MKLocalSearch.Request()
                request.naturalLanguageQuery = "\(location.coordinate.latitude),\(location.coordinate.longitude)"
                request.region = MKCoordinateRegion(
                    center: location.coordinate,
                    span: MKCoordinateSpan(latitudeDelta: 0.01, longitudeDelta: 0.01)
                )

                let search = MKLocalSearch(request: request)
                let response = try await search.start()

                guard let mapItem = response.mapItems.first else {
                    await MainActor.run {
                        self.currentLocationName = "Unknown Location"
                    }
                    return
                }

                await MainActor.run {
                    // Build a nice location name from MKMapItem
                    var components: [String] = []

                    // Try to get business/place name first
                    if let name = mapItem.name, !name.isEmpty {
                        components.append(name)
                    }

                    // Use modern iOS 26+ API: address property instead of placemark
                    if #available(iOS 26.0, *) {
                        // Use the new address property which returns an MKAddress
                        if let address = mapItem.address {
                            // MKAddress should have street and city properties
                            // Try to access them dynamically since API might still be in flux
                            let mirror = Mirror(reflecting: address)
                            var street: String?
                            var city: String?

                            for child in mirror.children {
                                if let label = child.label {
                                    if label.lowercased().contains("street") || label.lowercased().contains("thoroughfare") {
                                        street = child.value as? String
                                    } else if label.lowercased().contains("city") || label.lowercased().contains("locality") {
                                        city = child.value as? String
                                    }
                                }
                            }

                            if let street = street, !street.isEmpty,
                               !components.contains(where: { $0.contains(street) }) {
                                components.append(street)
                            }
                            if let city = city, !city.isEmpty {
                                components.append(city)
                            }
                        }
                    } else {
                        // iOS < 26: Use deprecated placemark property
                        let placemark = mapItem.placemark
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
                    }

                    let locationName = components.isEmpty ? "Unknown Location" : components.joined(separator: ", ")
                    self.currentLocationName = locationName

                    // Cache for next scan
                    self.lastLocationName = locationName
                    self.lastLocationLatitude = location.coordinate.latitude
                    self.lastLocationLongitude = location.coordinate.longitude

                    print("📍 Location: \(locationName)")
                }
            } catch {
                print("⚠️ Geocoding error: \(error.localizedDescription)")
                await MainActor.run {
                    self.currentLocationName = "Unknown Location"
                }
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

