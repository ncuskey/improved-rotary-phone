import SwiftUI
import SwiftData
import AVFoundation

struct ScannerReviewView: View {
    @Environment(\.modelContext) var modelContext
    @StateObject private var viewModel = ScannerViewModel()
    
    var body: some View {
        ZStack {
            DS.Color.background.ignoresSafeArea()
            
            VStack(spacing: 0) {
                // Top Section: Scanner/Input
                ScannerInputView(viewModel: viewModel)
                    .frame(height: viewModel.inputMode == .camera ? 280 : nil)
                    .background(Color.black)
                
                // Main Content
                ScrollView {
                    VStack(spacing: 16) {
                        if let eval = viewModel.evaluation {
                            // 1. Pricing & Market Data
                            ScannerPricingView(pricing: viewModel.pricing)
                            
                            // 2. Attributes & Condition
                            ScannerAttributesView(viewModel: viewModel)
                            
                            // 3. Analysis & Recommendation
                            ScannerResultView(viewModel: viewModel, eval: eval)
                            
                            // Spacer for bottom buttons
                            Color.clear.frame(height: 100)
                        } else if viewModel.isLoading || viewModel.isLoadingEvaluation {
                            loadingState
                        } else if let error = viewModel.errorMessage {
                            errorState(message: error)
                        } else if !viewModel.isScanning {
                            // Ready to scan state (if not scanning but no result)
                            Text("Ready to Scan")
                                .font(.headline)
                                .foregroundStyle(.secondary)
                                .padding(.top, 40)
                        }
                    }
                    .padding()
                }
                .refreshable {
                    viewModel.refreshData()
                }
            }
            
            // Floating Action Buttons
            if viewModel.evaluation != nil {
                VStack {
                    Spacer()
                    actionButtons
                }
            }
        }
        .navigationTitle("Scanner")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(action: { viewModel.showThresholdsSettings = true }) {
                    Image(systemName: "gear")
                }
            }
            
            ToolbarItem(placement: .topBarLeading) {
                if !viewModel.isScanning {
                    Button("Rescan") {
                        viewModel.rescan()
                    }
                }
            }
        }
        .sheet(isPresented: $viewModel.showThresholdsSettings) {
            DecisionThresholdsSettingsView(thresholds: $viewModel.thresholds)
        }
        .onAppear {
            viewModel.modelContext = modelContext
        }
        .onChange(of: modelContext) { _, newContext in
            viewModel.modelContext = newContext
        }
    }
    
    // MARK: - Subviews
    
    private var loadingState: some View {
        VStack(spacing: 16) {
            ProgressView()
                .scaleEffect(1.5)
            Text(viewModel.isLoadingEvaluation ? "Evaluating..." : "Looking up...")
                .font(.headline)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 60)
    }
    
    private func errorState(message: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle.fill")
                .font(.largeTitle)
                .foregroundStyle(.orange)
            Text(message)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
            Button("Try Again") {
                viewModel.rescan()
            }
            .buttonStyle(.bordered)
        }
        .padding()
        .padding(.top, 40)
    }
    
    private var actionButtons: some View {
        HStack(spacing: 16) {
            // REJECT Button
            Button(action: {
                viewModel.reject()
            }) {
                HStack {
                    Image(systemName: "xmark.circle.fill")
                    Text("Reject")
                }
                .fontWeight(.bold)
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .background(Color.red)
                .cornerRadius(12)
            }
            
            // ACCEPT Button
            Button(action: {
                viewModel.acceptAndContinue()
            }) {
                HStack {
                    Image(systemName: "checkmark.circle.fill")
                    Text("Accept")
                }
                .fontWeight(.bold)
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .background(Color.green)
                .cornerRadius(12)
            }
        }
        .padding()
        .background(
            DS.Color.background
                .opacity(0.95)
                .ignoresSafeArea(edges: .bottom)
        )
        .shadow(color: Color.black.opacity(0.1), radius: 5, x: 0, y: -2)
    }
}

// MARK: - Preview
#Preview {
    NavigationView {
        ScannerReviewView()
            .modelContainer(for: [CachedBook.self, CachedLot.self], inMemory: true)
    }
}
