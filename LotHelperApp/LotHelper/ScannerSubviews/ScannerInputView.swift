import SwiftUI

struct ScannerInputView: View {
    @ObservedObject var viewModel: ScannerViewModel
    
    var body: some View {
        Group {
            // Hidden scanner for bluetooth input
            HiddenScannerInput(
                isActive: viewModel.useHiddenScanner && viewModel.inputMode == .text,
                onSubmit: viewModel.handleScan
            )
            .frame(width: 0, height: 0)
            
            if viewModel.isScanning {
                if viewModel.inputMode == .camera {
                    // Camera mode
                    BarcodeScannerView(isActive: $viewModel.isScanning) { code in
                        viewModel.handleScan(code)
                    }
                    .background(Color.black)
                    .overlay(
                        ReticleView()
                            .padding(.horizontal, 28)
                    )
                } else if viewModel.inputMode == .text {
                    // Text entry mode
                    textInputArea
                        .background(DS.Color.cardBg)
                }
            }
        }
    }
    
    private var textInputArea: some View {
        VStack(spacing: DS.Spacing.md) {
            Text("Enter ISBN or Scan with Bluetooth")
                .font(.headline)
                .foregroundStyle(DS.Color.textPrimary)
            
            HStack(spacing: DS.Spacing.sm) {
                Image(systemName: "keyboard")
                    .foregroundStyle(DS.Color.textSecondary)
                
                // Custom TextField that forces keyboard
                ForceKeyboardTextField(
                    placeholder: "ISBN (978...)",
                    text: $viewModel.textInput,
                    onSubmit: viewModel.submitTextInput,
                    isFocused: $viewModel.isTextFieldFocused,
                    forceKeyboard: $viewModel.forceKeyboardVisible
                )
                .frame(height: 44)
                
                if !viewModel.textInput.isEmpty {
                    Button(action: { viewModel.textInput = "" }) {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundStyle(DS.Color.textSecondary)
                    }
                }
                
                Button(action: viewModel.submitTextInput) {
                    Image(systemName: "arrow.right.circle.fill")
                        .font(.title2)
                        .foregroundStyle(viewModel.textInput.isEmpty ? DS.Color.textSecondary : DS.Color.primary)
                }
                .disabled(viewModel.textInput.isEmpty)
            }
            .padding()
            .background(DS.Color.background, in: RoundedRectangle(cornerRadius: DS.Radius.md))
            .overlay(
                RoundedRectangle(cornerRadius: DS.Radius.md)
                    .stroke(viewModel.isTextFieldFocused ? DS.Color.primary : Color.clear, lineWidth: 2)
            )
        }
        .padding()
    }
}

// MARK: - Helper Views

struct ReticleView: View {
    var body: some View {
        RoundedRectangle(cornerRadius: 14)
            .strokeBorder(style: StrokeStyle(lineWidth: 2, dash: [10, 8]))
            .foregroundStyle(DS.Color.textSecondary.opacity(0.6))
            .frame(maxWidth: .infinity)
            .frame(height: 140)
            .accessibilityHidden(true)
    }
}

struct HiddenScannerInput: UIViewRepresentable {
    var isActive: Bool
    var onSubmit: (String) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onSubmit: onSubmit)
    }

    func makeUIView(context: Context) -> UITextField {
        let textField = UITextField(frame: .zero)
        textField.delegate = context.coordinator
        textField.autocorrectionType = .no
        textField.autocapitalizationType = .none
        textField.spellCheckingType = .no
        textField.returnKeyType = .done
        textField.enablesReturnKeyAutomatically = false
        textField.tintColor = .clear
        textField.textColor = .clear
        textField.backgroundColor = .clear

        // Prevent on-screen keyboard from appearing while still receiving hardware input.
        textField.inputView = UIView(frame: .zero)
        return textField
    }

    func updateUIView(_ textField: UITextField, context: Context) {
        if isActive {
            if !textField.isFirstResponder {
                DispatchQueue.main.async {
                    textField.becomeFirstResponder()
                }
            }
        } else {
            context.coordinator.reset()
            textField.text = ""
            // Resign immediately (not async) to allow visible TextField to take focus faster
            if textField.isFirstResponder {
                textField.resignFirstResponder()
            }
        }
    }

    final class Coordinator: NSObject, UITextFieldDelegate {
        private var buffer = ""
        private let onSubmit: (String) -> Void

        init(onSubmit: @escaping (String) -> Void) {
            self.onSubmit = onSubmit
        }

        func textField(_ textField: UITextField, shouldChangeCharactersIn range: NSRange, replacementString string: String) -> Bool {
            if string.isEmpty {
                if !buffer.isEmpty {
                    buffer.removeLast()
                }
                return false
            }

            let newlineSet = CharacterSet.newlines
            let pieces = string.components(separatedBy: newlineSet)

            for (index, piece) in pieces.enumerated() {
                if !piece.isEmpty {
                    buffer.append(piece)
                }

                let isLastPiece = index == pieces.count - 1
                if !isLastPiece {
                    commitBuffer(textField)
                }
            }

            return false
        }

        func reset() {
            buffer = ""
        }

        private func commitBuffer(_ textField: UITextField) {
            let trimmed = buffer.trimmingCharacters(in: .whitespacesAndNewlines)
            buffer = ""
            textField.text = ""

            if !trimmed.isEmpty {
                onSubmit(trimmed)
            }
        }
    }
}

/// Custom UITextField that forces software keyboard even with bluetooth keyboard
class AlwaysShowKeyboardTextField: UITextField {
    // Override to force software keyboard
    override var inputAccessoryView: UIView? {
        get { super.inputAccessoryView }
        set { super.inputAccessoryView = newValue }
    }
}

/// Custom TextField that forces on-screen keyboard even when bluetooth keyboard connected
struct ForceKeyboardTextField: UIViewRepresentable {
    let placeholder: String
    @Binding var text: String
    var onSubmit: () -> Void
    var isFocused: Binding<Bool>
    @Binding var forceKeyboard: Bool

    func makeCoordinator() -> Coordinator {
        Coordinator(text: $text, onSubmit: onSubmit, isFocused: isFocused)
    }

    func makeUIView(context: Context) -> AlwaysShowKeyboardTextField {
        let textField = AlwaysShowKeyboardTextField()
        textField.placeholder = placeholder
        textField.borderStyle = .roundedRect
        textField.keyboardType = .numberPad
        textField.autocorrectionType = .no
        textField.autocapitalizationType = .none
        textField.delegate = context.coordinator

        // This is the key: disable automatic keyboard suppression
        textField.inputAssistantItem.leadingBarButtonGroups = []
        textField.inputAssistantItem.trailingBarButtonGroups = []

        // Add toolbar with Done button above keyboard
        let toolbar = UIToolbar()
        toolbar.sizeToFit()
        let flexSpace = UIBarButtonItem(barButtonSystemItem: .flexibleSpace, target: nil, action: nil)
        let doneButton = UIBarButtonItem(title: "Done", style: .prominent, target: context.coordinator, action: #selector(Coordinator.doneButtonTapped))
        toolbar.items = [flexSpace, doneButton]
        textField.inputAccessoryView = toolbar

        return textField
    }

    func updateUIView(_ uiView: AlwaysShowKeyboardTextField, context: Context) {
        uiView.text = text

        // Check if we should force keyboard focus
        if forceKeyboard && !uiView.isFirstResponder {
            DispatchQueue.main.async {
                uiView.becomeFirstResponder()
                // Reload input views to ensure keyboard appears if possible
                uiView.reloadInputViews()
            }
            // Reset the trigger
            DispatchQueue.main.async {
                self.forceKeyboard = false
            }
        }

        // Handle normal focus state changes
        if isFocused.wrappedValue {
            if !uiView.isFirstResponder {
                DispatchQueue.main.async {
                    uiView.becomeFirstResponder()
                }
            }
        } else {
            if uiView.isFirstResponder {
                DispatchQueue.main.async {
                    uiView.resignFirstResponder()
                }
            }
        }
    }

    class Coordinator: NSObject, UITextFieldDelegate {
        @Binding var text: String
        var onSubmit: () -> Void
        var isFocused: Binding<Bool>

        init(text: Binding<String>, onSubmit: @escaping () -> Void, isFocused: Binding<Bool>) {
            _text = text
            self.onSubmit = onSubmit
            self.isFocused = isFocused
        }

        @objc func doneButtonTapped() {
            onSubmit()
        }

        func textFieldDidChangeSelection(_ textField: UITextField) {
            text = textField.text ?? ""
        }

        func textField(_ textField: UITextField, shouldChangeCharactersIn range: NSRange, replacementString string: String) -> Bool {
            // Update binding
            if let currentText = textField.text,
               let textRange = Range(range, in: currentText) {
                let updatedText = currentText.replacingCharacters(in: textRange, with: string)
                text = updatedText
            }
            return true
        }

        func textFieldShouldReturn(_ textField: UITextField) -> Bool {
            onSubmit()
            return true
        }

        func textFieldDidBeginEditing(_ textField: UITextField) {
            isFocused.wrappedValue = true
        }

        func textFieldDidEndEditing(_ textField: UITextField) {
            isFocused.wrappedValue = false
        }
    }
}
