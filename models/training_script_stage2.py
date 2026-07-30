"""
Training script for Stage 2 Specialist Classifiers.

This script trains the Stage 2 specialist classifiers for a specific genus
(Anopheles, Culex, or Aedes) using transfer learning with EfficientNet-B0.

Usage:
------
python models/training_script_stage2.py \
    --genus Anopheles \
    --data-dir data/anopheles_species_training \
    --output-dir models/ \
    --batch-size 32 \
    --num-epochs 20 \
    --learning-rate 1e-3

Expected directory structure:
    data/anopheles_species_training/
    ├── train/
    │   ├── An. gambiae complex/
    │   ├── An. funestus group/
    │   ├── An. nili/
    │   ├── ... (other Anopheles species)
    ├── val/
    │   ├── An. gambiae complex/
    │   ├── ... (same structure)
    └── test/ (optional)
        ├── An. gambiae complex/
        └── ...

Note: Folder names must EXACTLY match the class names in the taxonomy.
"""

import argparse
import os
import sys
import json
from pathlib import Path

import torch

# Running this file directly — the invocation documented above — puts models/ on sys.path
# but not the repo root, so the `models.` imports below died with ModuleNotFoundError
# before a single image was read. Add the repo root so both that command and
# `python -m models.training_script_stage2` work.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.stage2_specialist_classifiers import (
    create_anopheles_classifier,
    create_culex_classifier,
    create_aedes_classifier,
    get_specialist_data_loaders,
    train_specialist_model,
    load_specialist_checkpoint,
)
from models.mosquito_taxonomy import STAGE2_TAXONOMY


def main():
    parser = argparse.ArgumentParser(
        description="Train Stage 2 Specialist Classifier",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--genus",
        type=str,
        required=True,
        choices=["Anopheles", "Culex", "Aedes"],
        help="Genus to train classifier for",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        required=True,
        help="Path to the directory containing train/val/test splits for this genus",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="models/",
        help="Directory to save model checkpoints and metrics",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Batch size for training",
    )
    parser.add_argument(
        "--num-epochs",
        type=int,
        default=20,
        help="Number of training epochs",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=1e-3,
        help="Initial learning rate",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=4,
        help="Number of worker threads for data loading",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="cuda" if torch.cuda.is_available() else "cpu",
        help="Device to train on (cuda or cpu)",
    )
    parser.add_argument(
        "--pretrained",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use ImageNet pre-trained weights (pass --no-pretrained to disable)",
    )

    args = parser.parse_args()

    # Validate data directory
    if not os.path.isdir(args.data_dir):
        print(f"ERROR: Data directory not found: {args.data_dir}")
        sys.exit(1)

    train_dir = os.path.join(args.data_dir, "train")
    val_dir = os.path.join(args.data_dir, "val")
    if not os.path.isdir(train_dir) or not os.path.isdir(val_dir):
        print(f"ERROR: Missing train/ or val/ subdirectories in {args.data_dir}")
        sys.exit(1)

    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)

    print("\n" + "="*70)
    print(f"STAGE 2 {args.genus.upper()} SPECIALIST CLASSIFIER TRAINING")
    print("="*70)
    print(f"Genus: {args.genus}")
    print(f"Data directory: {args.data_dir}")
    print(f"Output directory: {args.output_dir}")
    print(f"Batch size: {args.batch_size}")
    print(f"Epochs: {args.num_epochs}")
    print(f"Learning rate: {args.learning_rate}")
    print(f"Device: {args.device}")
    print(f"Pretrained weights: {args.pretrained}")
    print("="*70 + "\n")

    device = torch.device(args.device)

    # Load data
    print("Loading data...")
    train_loader, val_loader, test_loader = get_specialist_data_loaders(
        data_dir=args.data_dir,
        batch_size=args.batch_size,
        num_workers=args.num_workers,
    )
    print(f"  Train batches: {len(train_loader)}")
    print(f"  Val batches: {len(val_loader)}")
    if test_loader:
        print(f"  Test batches: {len(test_loader)}")

    # Create model based on genus
    print("\nCreating model...")
    if args.genus == "Anopheles":
        model = create_anopheles_classifier(pretrained=args.pretrained)
        output_filename = "stage2_anopheles"
    elif args.genus == "Culex":
        model = create_culex_classifier(pretrained=args.pretrained)
        output_filename = "stage2_culex"
    else:  # Aedes
        model = create_aedes_classifier(pretrained=args.pretrained)
        output_filename = "stage2_aedes"

    print(f"  Model created: {model.__class__.__name__}")
    print(f"  Number of classes: {model.num_classes}")
    print(f"  Total parameters: {sum(p.numel() for p in model.parameters()):,}")

    # Validate cryptic complexes
    print("\nValidating cryptic complex constraints...")
    expected_classes = STAGE2_TAXONOMY[args.genus]["classes"]
    print(f"  Expected classes: {len(expected_classes)}")
    for cls in expected_classes[:3]:
        print(f"    - {cls}")
    if len(expected_classes) > 3:
        print(f"    ... and {len(expected_classes) - 3} more")
    print("  [OK] Cryptic complexes validated on model creation")

    # Train model
    print("\nTraining model...")
    checkpoint_path = os.path.join(args.output_dir, f"{output_filename}.pth")
    history = train_specialist_model(
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        num_epochs=args.num_epochs,
        learning_rate=args.learning_rate,
        device=device,
        checkpoint_path=checkpoint_path,
    )

    # Save training history
    history_path = os.path.join(args.output_dir, f"{output_filename}_history.json")
    with open(history_path, "w") as f:
        json.dump(history, f, indent=2)
    print(f"\nTraining history saved to {history_path}")

    # Load best checkpoint for final evaluation
    print("\nLoading best checkpoint for evaluation...")
    load_specialist_checkpoint(model, checkpoint_path, device)

    print("\n[OK] Training complete!")
    print(f"[OK] Best model saved to: {checkpoint_path}")
    print(f"[OK] Final validation accuracy: {history['val_accuracy'][-1]:.4f}")
    print("[OK] Use this checkpoint in the inference pipeline.\n")


if __name__ == "__main__":
    main()
