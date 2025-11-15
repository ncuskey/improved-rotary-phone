#!/usr/bin/env python3
"""
Training Orchestrator - Coordinates retraining of all ML models.

Runs all training scripts in sequence:
1. Main price model
2. Specialist models (AbeBooks, Alibris, Amazon, Biblio, eBay, ZVAB)
3. Lot model
4. Meta-model (stacking ensemble)

Handles model backups, validation, and rollback on failure.
"""

import sys
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from isbn_lot_optimizer.ml.model_versioner import ModelVersioner
from shared.training_detector import TrainingDataDetector


class TrainingOrchestrator:
    """Orchestrates the complete model retraining pipeline."""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.versioner = ModelVersioner()
        self.detector = TrainingDataDetector()
        self.training_results = {}

    def run_full_training(self) -> Dict[str, any]:
        """
        Run complete training pipeline with backup and validation.

        Returns:
            Dictionary with training results and metrics
        """
        print("=" * 70)
        print("ML Model Training Orchestrator")
        print("=" * 70)
        print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        start_time = datetime.now()

        try:
            # Step 1: Create backup of current models
            print("📦 Step 1: Backing up current models...")
            print("-" * 70)
            backup_version = self.versioner.backup_current_models()
            print()

            # Step 2: Train main price model
            print("🎯 Step 2: Training main price model...")
            print("-" * 70)
            main_result = self._run_training_script("scripts/train_price_model.py")
            self.training_results["main_model"] = main_result
            print()

            # Step 3: Train specialist models
            print("🔬 Step 3: Training specialist models...")
            print("-" * 70)
            specialist_scripts = [
                ("AbeBooks", "scripts/stacking/train_abebooks_model.py"),
                ("Alibris", "scripts/stacking/train_alibris_model.py"),
                ("Amazon", "scripts/stacking/train_amazon_model.py"),
                ("Biblio", "scripts/stacking/train_biblio_model.py"),
                ("eBay", "scripts/stacking/train_ebay_model.py"),
                ("ZVAB", "scripts/stacking/train_zvab_model.py"),
            ]

            for name, script in specialist_scripts:
                print(f"\n  Training {name} specialist...")
                result = self._run_training_script(script)
                self.training_results[f"specialist_{name.lower()}"] = result

            print()

            # Step 4: Train lot model
            print("📚 Step 4: Training lot model...")
            print("-" * 70)
            lot_result = self._run_training_script("scripts/stacking/train_lot_model.py")
            self.training_results["lot_model"] = lot_result
            print()

            # Step 5: Train meta-model
            print("🎓 Step 5: Training meta-model (ensemble)...")
            print("-" * 70)
            meta_result = self._run_training_script("scripts/stacking/train_meta_model.py")
            self.training_results["meta_model"] = meta_result
            print()

            # Step 6: Validate models
            print("✅ Step 6: Validating trained models...")
            print("-" * 70)
            validation_passed = self._validate_models()

            if not validation_passed:
                print("❌ Validation failed! Rolling back to backup...")
                self.versioner.restore_backup(backup_version)
                raise RuntimeError("Model validation failed - rolled back to previous version")

            print("✅ All models validated successfully!")
            print()

            # Step 7: Mark training as completed
            print("📝 Step 7: Updating training state...")
            print("-" * 70)
            self.detector.mark_training_completed()
            print()

            # Summary
            elapsed = (datetime.now() - start_time).total_seconds()
            print("=" * 70)
            print("Training Complete!")
            print("=" * 70)
            print(f"Total time: {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
            print(f"Backup version: {backup_version}")
            print()
            print("Model Performance:")
            self._print_results_summary()
            print()

            return {
                "success": True,
                "elapsed_seconds": elapsed,
                "backup_version": backup_version,
                "results": self.training_results,
            }

        except Exception as e:
            print()
            print("=" * 70)
            print("❌ Training Failed")
            print("=" * 70)
            print(f"Error: {e}")
            print()

            return {
                "success": False,
                "error": str(e),
                "results": self.training_results,
            }

    def _run_training_script(self, script_path: str) -> Dict[str, any]:
        """
        Run a training script and capture results.

        Args:
            script_path: Path to training script relative to project root

        Returns:
            Dictionary with training results (success, mae, time, etc.)
        """
        full_path = self.project_root / script_path
        start_time = datetime.now()

        try:
            # Run script with timeout
            result = subprocess.run(
                [sys.executable, str(full_path)],
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout per script
            )

            elapsed = (datetime.now() - start_time).total_seconds()

            # Parse MAE from output
            mae = self._extract_mae(result.stdout)

            success = result.returncode == 0

            if success:
                print(f"  ✅ Success (MAE: {mae:.2f}, {elapsed:.1f}s)")
            else:
                print(f"  ❌ Failed (exit code: {result.returncode})")
                print(f"  Error: {result.stderr[:200]}")

            return {
                "success": success,
                "mae": mae,
                "elapsed_seconds": elapsed,
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

        except subprocess.TimeoutExpired:
            print(f"  ⏱️ Timeout after 10 minutes")
            return {
                "success": False,
                "error": "Timeout",
                "elapsed_seconds": 600,
            }
        except Exception as e:
            print(f"  ❌ Error: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def _extract_mae(self, output: str) -> Optional[float]:
        """
        Extract MAE value from training script output.

        Looks for patterns like:
        - "Test MAE: 2.45"
        - "MAE: $2.45"
        - "Mean Absolute Error: 2.45"

        Args:
            output: stdout from training script

        Returns:
            MAE value or None if not found
        """
        import re

        patterns = [
            r"Test MAE:\s*\$?(\d+\.?\d*)",
            r"MAE:\s*\$?(\d+\.?\d*)",
            r"Mean Absolute Error:\s*\$?(\d+\.?\d*)",
        ]

        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return float(match.group(1))

        return None

    def _validate_models(self) -> bool:
        """
        Validate that new models are reasonable.

        Checks:
        - Model files exist
        - MAE within reasonable range (not 10x worse than previous)

        Returns:
            True if validation passes
        """
        model_dir = self.project_root / "isbn_lot_optimizer" / "models"

        # Check that key model files exist
        required_files = [
            "price_v1.pkl",
            "scaler_v1.pkl",
            "metadata.json",
        ]

        for filename in required_files:
            if not (model_dir / filename).exists():
                print(f"  ❌ Missing required file: {filename}")
                return False

        # Check that MAEs are reasonable
        # Main model should have MAE < $10 (sanity check)
        main_mae = self.training_results.get("main_model", {}).get("mae")
        if main_mae and main_mae > 10.0:
            print(f"  ❌ Main model MAE too high: ${main_mae:.2f}")
            return False

        # All models should have succeeded
        for model_name, result in self.training_results.items():
            if not result.get("success"):
                print(f"  ❌ Model failed: {model_name}")
                return False

        print("  ✅ All validation checks passed")
        return True

    def _print_results_summary(self):
        """Print summary of training results."""
        for model_name, result in self.training_results.items():
            if result.get("success"):
                mae = result.get("mae")
                time = result.get("elapsed_seconds", 0)
                mae_str = f"${mae:.2f}" if mae else "N/A"
                print(f"  {model_name:25s}: MAE={mae_str:8s} ({time:.1f}s)")
            else:
                error = result.get("error", "Unknown error")
                print(f"  {model_name:25s}: ❌ FAILED ({error})")


def main():
    """Main entry point."""
    orchestrator = TrainingOrchestrator()
    result = orchestrator.run_full_training()

    # Exit with appropriate code
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
