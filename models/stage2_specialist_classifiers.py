"""
Stage 2 Specialist Classifiers: Genus-specific Fine-grained Classification.

This module provides:
1. A specialist classifier class for each genus (Anopheles/Culex/Aedes)
2. Each classifier respects cryptic complex constraints (defined in mosquito_taxonomy.py)
3. Shared training infrastructure (can be reused for each genus)
4. Output classes that align with biological reality

IMPORTANT: Class definitions MUST be validated against mosquito_taxonomy.py
to ensure no individual cryptic complex members are used as separate outputs.

Example for Anopheles Stage 2 output classes:
- An. gambiae complex (NOT individual species like gambiae s.s., coluzzii, etc.)
- An. funestus group (NOT individual members like funestus s.s., rivulorum, etc.)
- An. nili, An. moucheti, An. pharoensis, etc. (individual species OK here)

Data structure for training:
    data/anopheles_species_training/
    ├── train/
    │   ├── An. gambiae complex/
    │   ├── An. funestus group/
    │   ├── An. nili/
    │   └── ...
    ├── val/
    │   ├── An. gambiae complex/
    │   ├── An. funestus group/
    │   ├── An. nili/
    │   └── ...
    └── test/ (optional)
        ├── An. gambiae complex/
        ├── An. funestus group/
        ├── An. nili/
        └── ...
"""

from typing import Dict, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import transforms, models
from torchvision.datasets import ImageFolder
import os

from models.mosquito_taxonomy import (
    validate_genus_classes,
    get_species_resolution_level,
    ANOPHELES_CLASSES,
    CULEX_CLASSES,
    AEDES_CLASSES,
)


# ========================================================================
# STAGE 2 SPECIALIST CLASSIFIER
# ========================================================================


class Stage2SpecialistClassifier(nn.Module):
    """
    Fine-tuned EfficientNet-B0 for genus-specific species/complex classification.
    
    This classifier respects cryptic complex constraints: complexes are treated
    as single output classes, never split into individual species members.
    
    Parameters
    ----------
    num_classes : int
        Number of output classes (genus-specific; e.g., 12 for Anopheles)
    genus : str
        The genus this classifier is trained for ("Anopheles", "Culex", or "Aedes")
    pretrained : bool
        Whether to use ImageNet pre-trained weights
    """

    def __init__(self, num_classes: int, genus: str = "Anopheles", pretrained: bool = True):
        super().__init__()
        self.num_classes = num_classes
        self.genus = genus

        # Load pre-trained EfficientNet-B0
        self.backbone = models.efficientnet_b0(pretrained=pretrained)

        # Replace the final classification layer
        self.backbone.classifier = nn.Sequential(
            nn.Dropout(p=0.2, inplace=True),
            nn.Linear(1280, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.backbone(x)

    def freeze_backbone(self) -> None:
        """Freeze all backbone parameters; only train the classification head."""
        for param in self.backbone.features.parameters():
            param.requires_grad = False

    def unfreeze_backbone(self) -> None:
        """Unfreeze all backbone parameters for fine-tuning."""
        for param in self.backbone.parameters():
            param.requires_grad = True


# ========================================================================
# FACTORY FUNCTIONS FOR GENUS-SPECIFIC CLASSIFIERS
# ========================================================================


def create_anopheles_classifier(pretrained: bool = True) -> Stage2SpecialistClassifier:
    """Create an Anopheles specialist classifier with proper class counts."""
    # CONSTRAINT CHECK: Validate that ANOPHELES_CLASSES respects cryptic complexes
    validate_genus_classes("Anopheles", ANOPHELES_CLASSES)
    return Stage2SpecialistClassifier(
        num_classes=len(ANOPHELES_CLASSES),
        genus="Anopheles",
        pretrained=pretrained,
    )


def create_culex_classifier(pretrained: bool = True) -> Stage2SpecialistClassifier:
    """Create a Culex specialist classifier with proper class counts."""
    validate_genus_classes("Culex", CULEX_CLASSES)
    return Stage2SpecialistClassifier(
        num_classes=len(CULEX_CLASSES),
        genus="Culex",
        pretrained=pretrained,
    )


def create_aedes_classifier(pretrained: bool = True) -> Stage2SpecialistClassifier:
    """Create an Aedes specialist classifier with proper class counts."""
    validate_genus_classes("Aedes", AEDES_CLASSES)
    return Stage2SpecialistClassifier(
        num_classes=len(AEDES_CLASSES),
        genus="Aedes",
        pretrained=pretrained,
    )


def create_stage2_classifiers(
    pretrained: bool = True,
) -> Dict[str, Stage2SpecialistClassifier]:
    """Create all three Stage 2 specialist classifiers."""
    return {
        "Anopheles": create_anopheles_classifier(pretrained),
        "Culex": create_culex_classifier(pretrained),
        "Aedes": create_aedes_classifier(pretrained),
    }


# ========================================================================
# TRAINING FUNCTIONS (Shared across all genera)
# ========================================================================


def get_specialist_data_transforms() -> Dict[str, transforms.Compose]:
    """Get the same transforms as Stage 1 (genus classifier)."""
    train_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomVerticalFlip(p=0.5),
        transforms.RandomRotation(degrees=15),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
        transforms.RandomAffine(degrees=0, translate=(0.1, 0.1)),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225],
        ),
    ])

    val_test_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225],
        ),
    ])

    return {
        "train": train_transform,
        "val": val_test_transform,
        "test": val_test_transform,
    }


def get_specialist_data_loaders(
    data_dir: str, batch_size: int = 32, num_workers: int = 4
) -> Tuple[DataLoader, DataLoader, Optional[DataLoader]]:
    """Load specialist data (genus-specific species/complex classes)."""
    transforms_dict = get_specialist_data_transforms()

    train_dir = os.path.join(data_dir, "train")
    val_dir = os.path.join(data_dir, "val")
    test_dir = os.path.join(data_dir, "test")

    train_dataset = ImageFolder(train_dir, transform=transforms_dict["train"])
    val_dataset = ImageFolder(val_dir, transform=transforms_dict["val"])

    test_dataset = None
    if os.path.exists(test_dir):
        test_dataset = ImageFolder(test_dir, transform=transforms_dict["test"])

    train_loader = DataLoader(
        train_dataset, batch_size=batch_size, shuffle=True, num_workers=num_workers
    )
    val_loader = DataLoader(
        val_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers
    )
    test_loader = None
    if test_dataset:
        test_loader = DataLoader(
            test_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers
        )

    return train_loader, val_loader, test_loader


def train_specialist_epoch(
    model: nn.Module,
    train_loader: DataLoader,
    criterion: nn.Module,
    optimizer: optim.Optimizer,
    device: torch.device,
) -> float:
    """Run one training epoch for a specialist classifier."""
    model.train()
    total_loss = 0.0
    for images, labels in train_loader:
        images, labels = images.to(device), labels.to(device)

        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()

        total_loss += loss.item() * images.size(0)

    return total_loss / len(train_loader.dataset)


def validate_specialist_epoch(
    model: nn.Module,
    val_loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
) -> Tuple[float, float]:
    """Run one validation epoch for a specialist classifier."""
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0

    with torch.no_grad():
        for images, labels in val_loader:
            images, labels = images.to(device), labels.to(device)

            outputs = model(images)
            loss = criterion(outputs, labels)

            total_loss += loss.item() * images.size(0)
            _, predicted = torch.max(outputs, 1)
            correct += (predicted == labels).sum().item()
            total += labels.size(0)

    avg_loss = total_loss / len(val_loader.dataset)
    accuracy = correct / total
    return avg_loss, accuracy


def train_specialist_model(
    model: Stage2SpecialistClassifier,
    train_loader: DataLoader,
    val_loader: DataLoader,
    num_epochs: int = 20,
    learning_rate: float = 1e-3,
    device: Optional[torch.device] = None,
    checkpoint_path: str = "stage2_specialist.pth",
) -> Dict[str, list]:
    """
    Train a Stage 2 specialist classifier (genus-specific).
    
    Same training strategy as Stage 1: frozen backbone for initial epochs,
    then fine-tuning.
    """
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model = model.to(device)
    criterion = nn.CrossEntropyLoss()

    freeze_epochs = max(1, num_epochs // 3)
    history = {"train_loss": [], "val_loss": [], "val_accuracy": []}
    best_val_acc = 0.0

    for epoch in range(num_epochs):
        if epoch == freeze_epochs:
            print(f"Epoch {epoch}: Unfreezing backbone for fine-tuning...")
            model.unfreeze_backbone()

        current_lr = learning_rate if epoch < freeze_epochs else learning_rate * 0.1
        optimizer = optim.Adam(model.parameters(), lr=current_lr)

        train_loss = train_specialist_epoch(model, train_loader, criterion, optimizer, device)
        val_loss, val_acc = validate_specialist_epoch(model, val_loader, criterion, device)

        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["val_accuracy"].append(val_acc)

        print(
            f"Epoch {epoch + 1}/{num_epochs} | "
            f"Train Loss: {train_loss:.4f} | "
            f"Val Loss: {val_loss:.4f} | "
            f"Val Accuracy: {val_acc:.4f}"
        )

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save(model.state_dict(), checkpoint_path)
            print(f"  -> Saved checkpoint to {checkpoint_path}")

    return history


def load_specialist_checkpoint(
    model: Stage2SpecialistClassifier,
    checkpoint_path: str,
    device: torch.device,
) -> None:
    """Load specialist model weights from a checkpoint."""
    state_dict = torch.load(checkpoint_path, map_location=device)
    model.load_state_dict(state_dict)
    print(f"Loaded checkpoint from {checkpoint_path}")


# ========================================================================
# INFERENCE FOR SPECIALIST CLASSIFIERS
# ========================================================================


def predict_species(
    model: Stage2SpecialistClassifier,
    image_tensor: torch.Tensor,
    device: torch.device,
    class_dict: Dict[int, str],
) -> Tuple[str, float, str]:
    """
    Predict the species/complex for a single image tensor.
    
    Returns
    -------
    tuple
        (predicted_class_name, confidence_score, resolution_level)
        where resolution_level is "species" or "complex"
    """
    model.eval()
    model = model.to(device)

    if image_tensor.ndim == 3:
        image_tensor = image_tensor.unsqueeze(0)

    image_tensor = image_tensor.to(device)

    with torch.no_grad():
        outputs = model(image_tensor)
        probabilities = torch.softmax(outputs, dim=1)
        confidence, predicted_idx = torch.max(probabilities, 1)

    predicted_class = class_dict[predicted_idx.item()]
    confidence_score = confidence.item()
    resolution = get_species_resolution_level(model.genus, predicted_class)

    return predicted_class, confidence_score, resolution


if __name__ == "__main__":
    print("Stage 2 Specialist Classifiers Module Loaded")
    print("\nCreating specialist classifiers...")
    classifiers = create_stage2_classifiers()
    for genus, clf in classifiers.items():
        print(f"  {genus}: {clf.num_classes} classes")
