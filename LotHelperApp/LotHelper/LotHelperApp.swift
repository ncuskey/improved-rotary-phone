//
//  LotHelperApp.swift
//  LotHelper
//
//  Created by Nicholas Cuskey on 10/3/25.
//

import SwiftUI
import SwiftData
import UIKit

@main
struct LotHelperApp: App {

    init() {
        // One-time database cleanup before any other initialization
        Self.cleanupDatabaseFiles()
        let background = UIColor(named: "AppBackground") ?? .systemBackground

        configureURLCache()

        // Ensure the root hosting controller's window uses the app background color.
        UIWindow.appearance().backgroundColor = background

        // Keep tab bars opaque so their safe areas do not reveal a black window.
        let tabAppearance = UITabBarAppearance()
        tabAppearance.configureWithOpaqueBackground()
        tabAppearance.backgroundColor = background
        UITabBar.appearance().standardAppearance = tabAppearance
        UITabBar.appearance().scrollEdgeAppearance = tabAppearance
        UITabBar.appearance().isTranslucent = false

        if #available(iOS 15.0, *) {
            let navAppearance = UINavigationBarAppearance()
            navAppearance.configureWithOpaqueBackground()
            navAppearance.backgroundColor = background
            UINavigationBar.appearance().standardAppearance = navAppearance
            UINavigationBar.appearance().scrollEdgeAppearance = navAppearance
            UINavigationBar.appearance().compactAppearance = navAppearance
        }
    }

    private static func cleanupDatabaseFiles() {
        // This runs BEFORE anything else - when database files are not yet open

        // Check if we already did a cleanup for this version
        let cleanupKey = "DatabaseCleanupV1_Completed"
        if UserDefaults.standard.bool(forKey: cleanupKey) {
            return // Already cleaned up
        }

        guard let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else {
            return
        }

        // Check if database exists
        let storeURL = appSupport.appendingPathComponent("default.store")
        guard FileManager.default.fileExists(atPath: storeURL.path) else {
            // No database to clean, mark cleanup as done
            UserDefaults.standard.set(true, forKey: cleanupKey)
            return
        }

        print("🧹 One-time database cleanup - removing old database files...")

        // Delete all database files (main store, WAL, SHM, etc.)
        let storeFiles = ["default.store", "default.store-wal", "default.store-shm"]
        for filename in storeFiles {
            let fileURL = appSupport.appendingPathComponent(filename)
            if FileManager.default.fileExists(atPath: fileURL.path) {
                do {
                    try FileManager.default.removeItem(at: fileURL)
                    print("🗑️ Deleted \(filename)")
                } catch {
                    print("⚠️ Failed to delete \(filename): \(error)")
                }
            }
        }

        // Mark cleanup as complete
        UserDefaults.standard.set(true, forKey: cleanupKey)
        print("✅ Database cleanup complete")
    }

    private func configureURLCache() {
        let memoryCapacity = 50 * 1024 * 1024 // 50 MB
        let diskCapacity = 200 * 1024 * 1024 // 200 MB
        let cache = URLCache(memoryCapacity: memoryCapacity, diskCapacity: diskCapacity)
        URLCache.shared = cache
    }

    var sharedModelContainer: ModelContainer = {
        let schema = Schema([
            Item.self,
            CachedBook.self,
            CachedLot.self,
        ])

        // Use in-memory storage to avoid database corruption issues during development
        let modelConfiguration = ModelConfiguration(
            schema: schema,
            isStoredInMemoryOnly: true  // Changed to true to avoid persistent storage issues
        )

        do {
            let container = try ModelContainer(for: schema, configurations: [modelConfiguration])
            print("✅ ModelContainer created successfully (in-memory)")
            return container
        } catch {
            print("❌ Failed to create ModelContainer: \(error)")
            fatalError("Could not create ModelContainer. Delete the app and reinstall.")
        }
    }()

    @State private var isLoading = true
    @State private var loadingStatus = "Initializing app..."

    var body: some Scene {
        WindowGroup {
            ZStack {
                if isLoading {
                    SplashScreenView(loadingStatus: loadingStatus)
                        .transition(.opacity)
                } else {
                    ContentView()
                        .brandTheme()
                        .background(DS.Color.background)
                        .transition(.opacity)
                }
            }
            .task {
                await performStartup()
            }
        }
        .modelContainer(sharedModelContainer)
    }

    private func performStartup() async {
        // Show initialization status
        await MainActor.run {
            loadingStatus = "Setting up database..."
        }

        // Simulate checking database (since we're in-memory, this is quick)
        try? await Task.sleep(nanoseconds: 500_000_000) // 0.5 seconds

        await MainActor.run {
            loadingStatus = "Loading cached data..."
        }

        // Give time for cache manager to initialize
        try? await Task.sleep(nanoseconds: 500_000_000) // 0.5 seconds

        await MainActor.run {
            loadingStatus = "Ready!"
        }

        // Brief pause to show "Ready!" message
        try? await Task.sleep(nanoseconds: 300_000_000) // 0.3 seconds

        // Fade out splash screen
        await MainActor.run {
            withAnimation(.easeOut(duration: 0.3)) {
                isLoading = false
            }
        }
    }
}
