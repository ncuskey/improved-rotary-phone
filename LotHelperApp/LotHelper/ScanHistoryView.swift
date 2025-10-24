//
//  ScanHistoryView.swift
//  LotHelper
//
//  View for browsing scan history with location data
//

import SwiftUI

struct ScanHistoryView: View {
    @State private var scans: [ScanHistoryRecord] = []
    @State private var locations: [ScanLocationSummary] = []
    @State private var stats: ScanStatistics?
    @State private var isLoading = false
    @State private var selectedFilter: FilterOption = .all
    @State private var selectedLocation: String?
    @State private var errorMessage: String?

    enum FilterOption: String, CaseIterable {
        case all = "All"
        case accepted = "Accepted"
        case rejected = "Rejected"

        var decision: String? {
            switch self {
            case .all: return nil
            case .accepted: return "ACCEPT"
            case .rejected: return "REJECT"
            }
        }
    }

    var body: some View {
        NavigationView {
            List {
                // Statistics Section
                if let stats = stats {
                    Section("Summary") {
                        statsRow(icon: "books.vertical.fill", label: "Total Scans", value: "\(stats.totalScans)")
                        statsRow(icon: "checkmark.circle.fill", label: "Accepted", value: "\(stats.accepted)", color: .green)
                        statsRow(icon: "xmark.circle.fill", label: "Rejected", value: "\(stats.rejected)", color: .red)
                        statsRow(icon: "mappin.circle.fill", label: "Locations", value: "\(stats.uniqueLocations)", color: .blue)
                    }
                }

                // Location Filters
                if !locations.isEmpty {
                    Section("Locations") {
                        ForEach(locations) { location in
                            Button {
                                selectedLocation = selectedLocation == location.locationName ? nil : location.locationName
                                Task {
                                    await loadScans()
                                }
                            } label: {
                                HStack {
                                    VStack(alignment: .leading) {
                                        Text(location.locationName)
                                            .font(.subheadline)
                                            .foregroundStyle(.primary)
                                        Text("\(location.scanCount) scans • \(String(format: "%.0f", location.acceptanceRate))% accepted")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                    Spacer()
                                    if selectedLocation == location.locationName {
                                        Image(systemName: "checkmark")
                                            .foregroundStyle(.blue)
                                    }
                                }
                            }
                        }
                    }
                }

                // Scan History
                Section {
                    Picker("Filter", selection: $selectedFilter) {
                        ForEach(FilterOption.allCases, id: \.self) { option in
                            Text(option.rawValue).tag(option)
                        }
                    }
                    .pickerStyle(.segmented)
                    .onChange(of: selectedFilter) { _, _ in
                        Task {
                            await loadScans()
                        }
                    }
                } header: {
                    Text("Scan History")
                } footer: {
                    if let location = selectedLocation {
                        Text("Filtered by: \(location)")
                    }
                }

                if scans.isEmpty && !isLoading {
                    ContentUnavailableView(
                        "No Scans Yet",
                        systemImage: "barcode.viewfinder",
                        description: Text("Your scan history will appear here")
                    )
                } else {
                    ForEach(scans) { scan in
                        ScanHistoryRow(scan: scan)
                    }
                }
            }
            .navigationTitle("Scan History")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .primaryAction) {
                    Button {
                        Task {
                            await loadAll()
                        }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                }
            }
            .task {
                await loadAll()
            }
            .refreshable {
                await loadAll()
            }
            .overlay {
                if isLoading {
                    ProgressView()
                }
            }
            .alert("Error", isPresented: .constant(errorMessage != nil)) {
                Button("OK") {
                    errorMessage = nil
                }
            } message: {
                if let error = errorMessage {
                    Text(error)
                }
            }
        }
    }

    @ViewBuilder
    private func statsRow(icon: String, label: String, value: String, color: Color = .primary) -> some View {
        HStack {
            Image(systemName: icon)
                .foregroundStyle(color)
            Text(label)
            Spacer()
            Text(value)
                .bold()
                .foregroundStyle(color)
        }
    }

    @MainActor
    private func loadAll() async {
        isLoading = true
        defer { isLoading = false }

        await withTaskGroup(of: Void.self) { group in
            group.addTask { await self.loadScans() }
            group.addTask { await self.loadLocations() }
            group.addTask { await self.loadStats() }
        }
    }

    private func loadScans() async {
        do {
            let fetchedScans = try await BookAPI.getScanHistory(
                limit: 100,
                locationName: selectedLocation,
                decision: selectedFilter.decision
            )
            await MainActor.run {
                scans = fetchedScans
            }
        } catch {
            await MainActor.run {
                errorMessage = "Failed to load scans: \(error.localizedDescription)"
            }
        }
    }

    private func loadLocations() async {
        do {
            let fetchedLocations = try await BookAPI.getScanLocations()
            await MainActor.run {
                locations = fetchedLocations
            }
        } catch {
            print("Failed to load locations: \(error)")
        }
    }

    private func loadStats() async {
        do {
            let fetchedStats = try await BookAPI.getScanStats()
            await MainActor.run {
                stats = fetchedStats
            }
        } catch {
            print("Failed to load stats: \(error)")
        }
    }
}

struct ScanHistoryRow: View {
    let scan: ScanHistoryRecord

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                // Decision indicator
                Image(systemName: decisionIcon)
                    .foregroundStyle(decisionColor)
                    .font(.caption)

                Text(scan.title ?? scan.isbn)
                    .font(.subheadline)
                    .fontWeight(.medium)

                Spacer()

                if let price = scan.estimatedPrice {
                    Text("$\(String(format: "%.2f", price))")
                        .font(.caption)
                        .fontWeight(.semibold)
                        .foregroundStyle(.secondary)
                }
            }

            if let authors = scan.authors {
                Text(authors)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            HStack(spacing: 12) {
                // Timestamp
                Text(formatDate(scan.scannedAt))
                    .font(.caption2)
                    .foregroundStyle(.tertiary)

                // Location
                if let location = scan.locationName {
                    Label(location, systemImage: "mappin.circle.fill")
                        .font(.caption2)
                        .foregroundStyle(.blue)
                }
            }

            // Notes
            if let notes = scan.notes {
                Text(notes)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .italic()
            }
        }
        .padding(.vertical, 4)
    }

    private var decisionIcon: String {
        switch scan.decision {
        case "ACCEPT": return "checkmark.circle.fill"
        case "REJECT": return "xmark.circle.fill"
        default: return "questionmark.circle.fill"
        }
    }

    private var decisionColor: Color {
        switch scan.decision {
        case "ACCEPT": return .green
        case "REJECT": return .red
        default: return .gray
        }
    }

    private func formatDate(_ dateString: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

        if let date = formatter.date(from: dateString) {
            let relativeFormatter = RelativeDateTimeFormatter()
            relativeFormatter.unitsStyle = .short
            return relativeFormatter.localizedString(for: date, relativeTo: Date())
        }

        return dateString
    }
}

#Preview {
    ScanHistoryView()
}
