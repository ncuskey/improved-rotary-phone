"""
Model versioning and backup system.

Handles safe model updates with automatic backups and rollback capability.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional


class ModelVersioner:
    """Manages model versions with automatic backups."""

    def __init__(self, model_dir: Optional[Path] = None, max_backups: int = 10):
        """
        Initialize the versioner.

        Args:
            model_dir: Directory containing model files
            max_backups: Maximum number of backup versions to keep
        """
        if model_dir is None:
            # Default to standard model directory
            import os
            project_root = Path(__file__).parent.parent.parent
            model_dir = project_root / "isbn_lot_optimizer" / "models"

        self.model_dir = Path(model_dir)
        self.max_backups = max_backups
        self.backup_dir = self.model_dir / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def backup_current_models(self) -> str:
        """
        Create backup of current production models.

        Returns:
            Backup version string (timestamp)
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Files to backup
        production_files = [
            "price_v1.pkl",
            "scaler_v1.pkl",
            "metadata.json",
        ]

        # Also backup stacking models
        stacking_dir = self.model_dir / "stacking"
        if stacking_dir.exists():
            production_files.extend([
                f"stacking/{f}" for f in [
                    "abebooks_model.pkl", "abebooks_scaler.pkl", "abebooks_metadata.json",
                    "alibris_model.pkl", "alibris_scaler.pkl", "alibris_metadata.json",
                    "amazon_model.pkl", "amazon_scaler.pkl", "amazon_metadata.json",
                    "biblio_model.pkl", "biblio_scaler.pkl", "biblio_metadata.json",
                    "ebay_model.pkl", "ebay_scaler.pkl", "ebay_metadata.json",
                    "zvab_model.pkl", "zvab_scaler.pkl", "zvab_metadata.json",
                    "lot_model.pkl", "lot_scaler.pkl", "lot_metadata.json",
                    "meta_model.pkl", "meta_metadata.json",
                ]
            ])

        # Create backup directory for this version
        backup_version_dir = self.backup_dir / f"v_{timestamp}"
        backup_version_dir.mkdir(parents=True, exist_ok=True)

        # Copy files
        backed_up = []
        for file_path in production_files:
            source = self.model_dir / file_path
            if source.exists():
                # Preserve directory structure
                dest = backup_version_dir / file_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
                backed_up.append(file_path)

        print(f"✅ Backed up {len(backed_up)} files to: {backup_version_dir.name}")

        # Clean up old backups
        self._cleanup_old_backups()

        return timestamp

    def restore_backup(self, version: str):
        """
        Restore models from a backup version.

        Args:
            version: Version timestamp (e.g., "20250111_143022")
        """
        backup_version_dir = self.backup_dir / f"v_{version}"

        if not backup_version_dir.exists():
            raise ValueError(f"Backup version not found: {version}")

        print(f"🔄 Restoring models from backup: {version}")

        # Find all files in backup
        restored = 0
        for backup_file in backup_version_dir.rglob("*"):
            if backup_file.is_file():
                # Compute relative path
                rel_path = backup_file.relative_to(backup_version_dir)
                dest = self.model_dir / rel_path

                # Restore file
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_file, dest)
                restored += 1

        print(f"✅ Restored {restored} files from backup")

    def list_backups(self) -> List[dict]:
        """
        List all available backup versions.

        Returns:
            List of backup info dicts with version and metadata
        """
        backups = []

        for backup_dir in sorted(self.backup_dir.glob("v_*"), reverse=True):
            version = backup_dir.name.replace("v_", "")

            # Try to read metadata
            metadata_file = backup_dir / "metadata.json"
            metadata = {}
            if metadata_file.exists():
                try:
                    with open(metadata_file) as f:
                        metadata = json.load(f)
                except:
                    pass

            backups.append({
                "version": version,
                "timestamp": version,
                "path": str(backup_dir),
                "mae": metadata.get("test_mae"),
                "train_date": metadata.get("train_date"),
            })

        return backups

    def _cleanup_old_backups(self):
        """Remove old backup versions beyond max_backups."""
        backups = sorted(self.backup_dir.glob("v_*"), reverse=True)

        # Keep only max_backups most recent
        for old_backup in backups[self.max_backups:]:
            print(f"🗑️  Removing old backup: {old_backup.name}")
            shutil.rmtree(old_backup)


if __name__ == "__main__":
    # Test the versioner
    versioner = ModelVersioner()

    print("=" * 70)
    print("Model Versioner - Status Check")
    print("=" * 70)
    print()

    # List existing backups
    backups = versioner.list_backups()
    print(f"Existing backups: {len(backups)}")

    for backup in backups[:5]:  # Show first 5
        print(f"  {backup['version']}: MAE={backup.get('mae', 'N/A')}")

    print()

    # Create a test backup
    print("Creating backup of current models...")
    version = versioner.backup_current_models()
    print(f"✅ Backup created: {version}")

    print()
    print("=" * 70)
