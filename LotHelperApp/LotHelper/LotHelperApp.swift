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
        let background = UIColor(named: "AppBackground") ?? .systemBackground

        // Delete old incompatible database
        deleteOldDatabaseIfNeeded()

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

    private func deleteOldDatabaseIfNeeded() {
        // Find and delete the SwiftData store to force recreation with new schema
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
        if let appSupport = appSupport {
            let storeURL = appSupport.appendingPathComponent("default.store")
            if FileManager.default.fileExists(atPath: storeURL.path) {
                try? FileManager.default.removeItem(at: storeURL)
                print("Deleted old database at \(storeURL)")
            }
        }
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

        let modelConfiguration = ModelConfiguration(
            schema: schema,
            isStoredInMemoryOnly: false
        )

        do {
            return try ModelContainer(for: schema, configurations: [modelConfiguration])
        } catch {
            fatalError("Could not create ModelContainer: \(error)")
        }
    }()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .brandTheme()
                .background(DS.Color.background)
        }
        .modelContainer(sharedModelContainer)
    }
}
